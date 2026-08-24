# gen217 MCTS value distillation

The native MCTS evaluator is distilled from complete-turn gen217 self-play
positions. Its teacher target is the immediate searched win/loss value
`globalTargetsNC[16] - globalTargetsNC[17]`.

## Features

The rich model uses 18 scalar inputs:

- territory: `t1`, `t2`, `c1`, `c2`, `w`, exclusive territory, and contested
  territory;
- mobility: the legacy mobility score, total and weakest-queen direct mobility,
  mobility balance, liberties, weakest liberties, trapped queens, and overlapping
  queen reach;
- position and phase: center control, queen spread, and remaining empty squares.

For every empty square, `c1` accumulates the difference between exponentially
decayed QueenMove distances. `c2` accumulates the clipped KingMove distance
margin:

```text
c1 += 2^(-currentQueenDistance) - 2^(-opponentQueenDistance)
c2 += clamp((opponentKingDistance - currentKingDistance) / 6, -1, 1)
```

The deployed rich evaluator is a smooth phase-dependent formula. Every feature
coefficient is a cubic polynomial of the game phase `w / 92`, and its bounded
output is

```text
value = tanh((bias(w) + sum(feature[i] * coefficient[i](w))) / 2)
```

Deployment blends 50% of this formula with 50% of the earlier four-feature
gen217 model. A 64-unit ReLU MLP was also fitted, but head-to-head testing found
the formula blend stronger and cheaper to evaluate.

## Reproduce

Extract features and fit:

```powershell
python scripts/fit_mcts_value.py `
  --selfplay-tar <selfplay_gen217.tar> `
  --feature-cache <gen217_rich_features.npz> `
  --model-type formula --formula-phase w --formula-degree 3 `
  --formula-features t1,t2,c1,c2,mobility,empty_count,secure_territory,contested_count,queen_mobility,weakest_queen_mobility,queen_mobility_balance,liberties,weakest_liberties,trapped_queens,reach_overlap,center_control,queen_spread `
  --output src/ai/value_model_gen217.json
```

Export the dependency-free C++ header:

```powershell
python scripts/export_value_model_header.py `
  src/ai/value_model_gen217.json `
  src/ai/src/value_model_gen217.h
```

After compiling a module, verify every feature and the rich-model output:

```powershell
python scripts/check_value_feature_parity.py `
  --module-dir <compiled-module-directory> `
  --selfplay-tar <selfplay_gen217.tar> `
  --samples 256
```

## Results and limitation

On the held-out game split, the formula reaches RMSE `0.52499`, Spearman
correlation `0.37918`, and sign accuracy `63.137%`. The 64-unit rich MLP reached
RMSE `0.51537`, Spearman `0.38917`, and sign accuracy `63.691%`; the earlier
four-feature model reached RMSE `0.51761`, Spearman `0.36925`, and sign accuracy
`61.899%`. Although the formula is slightly worse at teacher-value regression,
its smooth phase behavior worked better inside MCTS.

The earlier 75%-legacy/25%-MLP blend scored 12-8 (60%) against the original
evaluator at 3 seconds per move. Formula screening at 0.05 seconds per move gave
11-13 for the pure rich formula, 14-10 for the 50%-legacy/50%-formula blend,
13-11 for the 75%-legacy/25%-formula blend, and 10-14 for the five-feature core
formula, all against the MLP deployment. A 32-game retest at 0.2 seconds gave
25-7 (78.125%) for the selected 50/50 formula blend against the MLP deployment.

At 3 seconds per move, the selected formula blend scored 14-6 (70%) against the
original evaluator. Colors alternated, four games ran concurrently, and each
active engine was capped at five OpenMP threads. Average root attempts per move
were 572,207 for the formula blend and 562,635 for the original evaluator.

This is a stronger engineering result than the MLP blend, but 20 games still
has a wide confidence interval and is not proof of a stable crushing advantage.
The formula discards most board geometry and does not preserve gen217's policy.
A larger strength gain should distill the three-stage policy and use it as a
PUCT prior, or invoke the neural policy/value model directly in batched search.

## Fine-grained mobility experiment

A second formula experiment split mobility into 15 additional statistics:
second-weakest and strongest queen mobility, raw local-mobility order
statistics, long-ray count, squared ray length, destination liberties, second
liberties, and immobile/cramped queen counts. On the held-out split, all 33
features improved RMSE from `0.52499` to `0.52347`, Spearman correlation from
`0.37918` to `0.38774`, and sign accuracy from `63.137%` to `63.640%`.

The result did not justify deployment. Against the deployed 18-feature formula,
the 33-feature candidate scored 19-13 at 0.05 seconds per move but only 17-15 at
0.2 seconds. Feature-group ablations scored 13-11 for queen order statistics
and 11-13 for long-ray features. Weakening regularization improved offline RMSE
but scored 10-14 in the short match.

Alternative teachers also failed the match screen: a 25% raw-gen217-NN target
blend scored 13-11, a 50% blend scored 10-14, and slow/medium/fast temporal-
difference targets scored 9-15, 11-13, and 13-11. These candidates and their
feature caches remain outside the repository for further analysis; production
continues to use the tested 18-feature immediate-search formula.

## Structural feature experiment

Research on strong Amazons evaluators and endgame solvers motivated five new
feature groups. Each group has a compile-time switch, so an ablation pays only
for the structure it actually uses:

- combat: mobility on one-move destinations which the opponent can still
  reach, plus the weakest queen's combat mobility;
- areas: 8-connected active-area queen counts, active area count, and redundant
  queens already committed to exclusive areas;
- gates: articulation queens, their separated-space swing, and control of
  contested articulation squares;
- assignment: per-queen contested-space load, load balance, and redundant
  fastest access;
- endgame: dead-end and articulation risk inside exclusive territories.

Python and C++ implementations were checked on 256 real gen217 positions. The
maximum feature error was `8.882e-15` and the maximum fitted-value error was
`9.465e-15`.

Held-out metrics show that the expensive queen-assignment group contains most
of the extra teacher information, while the best fit uses all 31 features:

| Formula | Test RMSE | Spearman | Sign accuracy |
| --- | ---: | ---: | ---: |
| deployed 18-feature refit | 0.52499 | 0.37918 | 63.137% |
| combat | 0.52349 | 0.38709 | 63.626% |
| areas | 0.52425 | 0.37837 | 63.057% |
| gates | 0.52354 | 0.38130 | 62.989% |
| assignment | 0.51960 | 0.40910 | 64.462% |
| endgame | 0.52500 | 0.37833 | 63.076% |
| assignment + combat | 0.51888 | 0.41277 | 64.737% |
| assignment + topology | 0.51629 | 0.41412 | 64.444% |
| all 31 features | **0.51567** | **0.41835** | **64.705%** |

Fixed-time games reverse much of the offline ranking. The full model is too
expensive and scored only 7-17 at 0.05 seconds per move. Assignment alone and
assignment plus combat both scored 10-14. A low-cost topology/combat formula
scored 11-13, areas scored 11-13, and gates scored 12-12. Blending only 25% of
the new formula into the deployed rich formula did not rescue the expensive
models: low-cost topology/combat scored 6-18 and assignment/combat scored 7-17.

The combat-only formula is the useful result. It adds almost no work to the
existing ray scan and won consistently at all three tested time controls:

| Seconds/move | Score vs deployed baseline | Win rate | Change from 50% | Candidate attempts/move | Baseline attempts/move |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 22-10 | **68.75%** | **+18.75 pp** | 23,223 | 20,347 |
| 0.2 | 24-16 | **60.00%** | **+10.00 pp** | 103,335 | 97,409 |
| 3.0 | 5-3 | **62.50%** | **+12.50 pp** | 663,660 | 647,610 |

The 3-second result is only an eight-game direction check and has a wide
confidence interval. Across different time controls the combat candidate scored
51-29, but those games should not be treated as one homogeneous statistical
sample. Production remains on the 18-feature evaluator until a larger long-time
match is accepted for deployment.

### Detailed combat-mobility follow-up

The fighting-mobility ray scan was further split into four zero-extra-scan
statistics: the second-weakest and strongest queen, per-side balance, and the
number of queens with nonzero fighting mobility. Appending all four did not
help in games. The useful ablation kept only the second-weakest and strongest
statistics. On the unchanged held-out game split it improved the combat
formula from RMSE `0.52349`, Spearman `0.38709`, and sign accuracy `63.626%` to
`0.52281`, `0.39056`, and `63.781%`.

The offline improvement was real but did not become a stable improvement over
the combat formula inside MCTS:

| Seconds/move | Score vs combat formula | Win rate | Candidate attempts/move | Combat attempts/move |
| ---: | ---: | ---: | ---: | ---: |
| 0.05 | 20-12 | 62.50% | 19,518 | 18,194 |
| 0.2 | 16-16 | 50.00% | 82,191 | 83,338 |
| 3.0, batch 1 | 5-3 | 62.50% | 644,264 | 623,757 |
| 3.0, batch 2 | 2-6 | 25.00% | 667,065 | 712,258 |

The two three-second batches combine to 7-9. Against the deployed 18-feature
baseline, the detailed candidate did score 21-11 (65.625%) at 0.2 seconds, but
that gain is mostly inherited from the already-tested combat formula. A
fifth-degree phase curve improved held-out RMSE further to `0.52023` and
Spearman to `0.39644`, then lost 10-14 to the cubic candidate at 0.05 seconds.
This is another example of better teacher regression not guaranteeing stronger
search. The detailed and higher-degree variants therefore remain experimental;
neither replaces the combat formula or the deployed evaluator.

The match runner supports independent concurrent games:

```powershell
python scripts/compare_mcts_builds.py `
  --module-a <candidate-module-directory> `
  --module-b <baseline-module-directory> `
  --games 20 --seconds 3 `
  --parallel-games 4 --engine-threads 5
```

## Three-stage policy distillation experiment

The gen217 archive contains 882,830 usable policy rows for the three decisions
in a complete Amazons turn. The labels are sharp and high quality: the
teacher's most-visited action carries 80.7%, 80.2%, and 78.5% of policy mass in
the queen, destination, and arrow stages. Each row has a median of about 1,160
search visits.

`src/ai/policy_fit.py` trains a 503-128-128 MLP with separate output heads for
the three stages. Games are split by hash, and eight board symmetries are used
only as training augmentation. On 84,439 held-out rows, teacher top-one match
was 38.2%, 38.7%, and 36.0%. The top-eight shortlist retained 95.9% of teacher
mass for destinations and 93.7% for arrows; top twelve retained 99.3% and
98.0%. The C++ implementation can use these scores to build only the Cartesian
product of shortlisted stage actions and can optionally use the resulting
complete-move probability in PUCT.

The first short-time result looked like the desired large gain: the 8x8
shortlist beat the deployed evaluator 18-6 at 0.05 seconds per move. It did not
survive the longer screen, scoring 14-18 at 0.2 seconds. Adding the combat
evaluator improved the 8x8 policy version 15-9 head-to-head, but that combined
candidate scored only 12-12 against the deployed baseline at 0.2 seconds. A
12x12 plus combat candidate recovered to 14-10 at 0.2 seconds, while losing
11-13 to the faster 8x8 version at 0.05 seconds. It also performs about 14-16%
fewer root attempts than the baseline.

PUCT, full-width root expansion, and earlier leaf expansion were not stable
improvements. PUCT beat the shortlist-only build 18-6 but scored only 14-10
against the baseline. Full-width root expansion beat the hard-shortlist build
17-7 but scored 12-12 against the baseline. Reducing the pre-expansion rollout
threshold from 40 to 8 scored 9-15 against the original threshold; a threshold
of 16 scored 12-12.

These policy switches remain compile-time experimental and default off. No
policy build is deployed. The experiment establishes that policy contains much
more useful information than another scalar value formula, but the small MLP
does not reproduce enough of gen217 to deliver a stable long-time crushing
advantage. The next serious candidate should use a compact convolutional or
residual policy model with an optimized batched CPU inference path, or query
the full gen217 policy/value network directly.

## Direct raw-network win-rate experiment

To distinguish the neural network's direct value from the value after teacher
search, a separate fit uses only `globalTargetsNC[57]`, documented by the data
writer as raw neural win-loss. The target is converted to win probability by
`p = (v + 1) / 2` for binary cross-entropy and converted back to `[-1,1]` by the
C++ evaluator. `raw-nn-weight` is 1 and `GEN217_LEGACY_BLEND` is 0, so neither
the immediate MCTS target nor the old four-feature value is mixed in. All
288,915 selected rows have columns 49 and 50 equal to zero, confirming that
none were generated by an older network than gen217.

The direct target is easier to approximate offline:

| Direct-value model | Test RMSE | Spearman | Sign accuracy |
| --- | ---: | ---: | ---: |
| core formula | 0.44604 | 0.43276 | 67.785% |
| combat formula | 0.44330 | 0.44400 | 68.064% |
| 64-unit combat MLP | **0.42986** | **0.46716** | **69.193%** |

Python/C++ parity on 256 gen217 positions had maximum value errors of
`8.105e-15` for the formula and `1.332e-15` for the MLP. UCT, six-step random
simulation, progressive widening, and move generation were unchanged.

Offline fit did not predict match strength. At 0.05 seconds, the combat formula
beat the core formula 15-9, while the MLP scored 11-13 against the combat
formula. The combat formula then scored 16-16 against production at 0.05
seconds and 7-17 at 0.2 seconds. The direct-value MLP produced two opposite
0.2-second batches, 12-4 and 7-17; combined it scored 19-21 (47.5%). This high
variance result is not evidence of an improvement, so no direct-value candidate
is deployed.
