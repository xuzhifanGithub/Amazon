#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <vector>
#include <stack>
#include <queue>
#include <string.h>
#include <algorithm>
#include <math.h>
#include <climits>
#include <array>
#include <functional>
#include <omp.h>
#include <cstdlib>
#include <windows.h>
#include <ctime>    // 用于 clock_t 和 clock()
#include <random>
#ifndef VALUE_MODEL_COMBAT
#define VALUE_MODEL_COMBAT 0
#endif
#ifndef VALUE_MODEL_COMBAT_DETAIL
#define VALUE_MODEL_COMBAT_DETAIL 0
#endif
#ifndef VALUE_MODEL_RAW_NN_CORE
#define VALUE_MODEL_RAW_NN_CORE 0
#endif
#ifndef VALUE_MODEL_RAW_NN_COMBAT
#define VALUE_MODEL_RAW_NN_COMBAT 0
#endif
#ifndef VALUE_MODEL_RAW_NN_MLP
#define VALUE_MODEL_RAW_NN_MLP 0
#endif
#if VALUE_MODEL_RAW_NN_MLP
#include "value_model_raw_nn_mlp64_combat.h"
#elif VALUE_MODEL_RAW_NN_COMBAT
#include "value_model_raw_nn_combat.h"
#elif VALUE_MODEL_RAW_NN_CORE
#include "value_model_raw_nn_core.h"
#elif VALUE_MODEL_COMBAT_DETAIL == 3
#include "value_model_gen217_combat_order_d5.h"
#elif VALUE_MODEL_COMBAT_DETAIL == 2
#include "value_model_gen217_combat_all.h"
#elif VALUE_MODEL_COMBAT_DETAIL == 1
#include "value_model_gen217_combat_order.h"
#elif VALUE_MODEL_COMBAT
#include "value_model_gen217_combat.h"
#else
#include "value_model_gen217.h"
#endif
#include "value_model_gen217_legacy.h"

#ifndef GEN217_POLICY_SHORTLIST
#define GEN217_POLICY_SHORTLIST 0
#endif
#if GEN217_POLICY_SHORTLIST
#include "policy_model_gen217.h"
#endif

#ifndef GEN217_POLICY_TO_WIDTH
#define GEN217_POLICY_TO_WIDTH 8
#endif
#ifndef GEN217_POLICY_ARROW_WIDTH
#define GEN217_POLICY_ARROW_WIDTH 8
#endif
#ifndef GEN217_POLICY_ORDER_WEIGHT
#define GEN217_POLICY_ORDER_WEIGHT 0.20
#endif
#ifndef GEN217_POLICY_FULL_ROOT
#define GEN217_POLICY_FULL_ROOT 0
#endif
#ifndef GEN217_POLICY_PUCT
#define GEN217_POLICY_PUCT 0
#endif
#ifndef GEN217_POLICY_PUCT_WEIGHT
#define GEN217_POLICY_PUCT_WEIGHT 1.0
#endif

#ifndef GEN217_BLEND_PRODUCTION_RICH
#define GEN217_BLEND_PRODUCTION_RICH 0
#endif
#ifndef GEN217_NEW_RICH_WEIGHT
#define GEN217_NEW_RICH_WEIGHT 1.0
#endif
#if GEN217_BLEND_PRODUCTION_RICH
#include "value_model_gen217_production.h"
#endif

#ifndef GEN217_LEGACY_BLEND
#define GEN217_LEGACY_BLEND 0.50
#endif

#ifndef GEN217_CALIBRATED_BLEND
#define GEN217_CALIBRATED_BLEND 0
#endif
#if GEN217_CALIBRATED_BLEND == 2
#include "value_blend_gen217_smooth.h"
#elif GEN217_CALIBRATED_BLEND
#include "value_blend_gen217.h"
#endif

#ifndef MCTS_SIMULATION_STEPS
#define MCTS_SIMULATION_STEPS 6
#endif
#ifndef UCT_LEAF_SIMULATION_THRESHOLD
#define UCT_LEAF_SIMULATION_THRESHOLD 40
#endif

// Structural feature groups are opt-in for experiments. Production builds keep
// them disabled unless their fitted model actually consumes the group, so an
// ablation pays only for the features being measured.
#ifndef VALUE_FEATURE_COMBAT
#define VALUE_FEATURE_COMBAT 0
#endif
#ifndef VALUE_FEATURE_AREAS
#define VALUE_FEATURE_AREAS 0
#endif
#ifndef VALUE_FEATURE_GATES
#define VALUE_FEATURE_GATES 0
#endif
#ifndef VALUE_FEATURE_ASSIGNMENT
#define VALUE_FEATURE_ASSIGNMENT 0
#endif
#ifndef VALUE_FEATURE_ENDGAME
#define VALUE_FEATURE_ENDGAME 0
#endif

static const int BOARD_SIZE = 10;
static const int BOARD_GRID_SIZE = 100;
static const int EVALUATION_FEATURE_COUNT = 35;
static const int EMPTY = 0;           // 空位
static const int RED_QUEEN = 1;       // 红方皇后
static const int BLUE_QUEEN = 2;      // 蓝方皇后
static const int STONE = 3;           // 障碍石头
static const int RED_SIDE = 1;        // 红方
static const int BLUE_SIDE = -1;      // 蓝方

static const int UCT_SELECT_NUMBER = 250; // UCT保留的节点数
static const int UCT_START_NUMBER = 5;//UCT一开始扩展的节点数
static const int UCT_ADD_WIDTH = 5;//UCT每1000次渐进拓宽的个数
static const int UCT_MAX_ATTEMPT_NUMBER = 5000000;//最大对局次数


static int dx[8] = { -1, -1, 0, 1, 1, 1, 0, -1 };
static int dy[8] = { 0, -1, -1, -1, 0, 1, 1, 1 };

static const bool isLegalArr[][12] = {
    {false,false,false,false,false,false,false,false,false,false,false,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,true,true,true,true,true,true,true,true,true,true,false},
    {false,false,false,false,false,false,false,false,false,false,false,false}
};

//using boardArray = std::array<std::array<int, BOARD_SIZE>, BOARD_SIZE>;
//using queenArray = std::array<std::array<int, 4>, 2>;
using boardArray = int[BOARD_SIZE][BOARD_SIZE];
using queenArray = int[2][4];
namespace py = pybind11;
struct MoveAction {
    int From;
    int To;
    int Stone;
};

struct MoveValue {
    MoveAction action;
    double value;
    double prior;
    double orderValue;
};

struct MoveMessage
{
    int side;
    double value;
    double r;
    double prior;
};

struct MovePro
{
    double valueSum;
    int attempt;
};

struct UCTNode
{
    MoveAction action;
    MoveMessage message;
    MovePro simulate;

    std::vector<MoveValue> vecMovePos;
    int expandSize;
    int maxSize;
    int depth;

    UCTNode* parent;
    std::vector<UCTNode*> vecNodes;

    boardArray nodeBoard;
    queenArray queenPos;
};

struct UctRes {
    int From;
    int To;
    int Stone;
    int attempt;
    double value;
    double pro;
};

struct COMP {
    bool operator()(MoveValue const& a, MoveValue const& b) {
        return a.orderValue > b.orderValue;
    }
};

//初始化相关
void initBoard(boardArray& board);
void initQueenPos(queenArray& queenPos);
void displayBoard(const boardArray& board);

//走法生成与规则相关
void updateQueenPos(queenArray& queenPos, int moveSide, int from, int to);
bool isWin(const boardArray& board, queenArray& queenPos, int moveSide);
bool isNeighborsHaveEmpty(const boardArray& board, int actionFrom);
std::vector<int> getExpandTerritory(const boardArray& board, int actionFrom);
std::vector<MoveAction> getSideQueenOneMoveAction(const boardArray& board, const queenArray& queenPos, int moveSide);
std::vector<MoveValue> getSideQueenMoveAction(boardArray& board, const  queenArray& queenPos, int moveSide);
void checkDisplayMoveValue(const std::vector<MoveValue>& vecMoveValue);
std::vector<MoveValue> getSideQueenMoveValue(boardArray& board,const queenArray& queenPos, int moveSide, int searchDepth);
#if GEN217_POLICY_SHORTLIST
std::vector<MoveValue> getSideQueenPolicyMoveAction(const boardArray& board, const queenArray& queenPos, int moveSide);
#endif

//估值相关
double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide, double* wValue);
double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide);
double valueT2(const boardArray& board, const queenArray& queenPos, int moveSide);
double valueMobility(const boardArray& board,const queenArray& queenPos, int moveSide);
int getNeighborsEmptyNumber(const boardArray& board, int actionFrom);
int getNeighborsEmptyNumber(const boardArray& board, int fromX, int fromY);
double calculateOneQueenMobilityValue(const boardArray& board, int kingPosX, int kingPosY);
std::array<double, EVALUATION_FEATURE_COUNT> calculateEvaluationFeatures(
    const boardArray& board, const queenArray& queenPos, int moveSide);
double evaluateFeatureArray(
    const std::array<double, EVALUATION_FEATURE_COUNT>& features);
double valueAll(const boardArray& board, const queenArray& queenPos, int moveSide);

//uct相关
UCTNode* uctInitNode(const boardArray& board, const queenArray& queenPos, UCTNode* head, int moveSide);
void deleteRoot(UCTNode* node);
UCTNode* uctSelect(UCTNode* node);
double uctGetR(UCTNode* node);
double uctSimulate(const boardArray& board, const queenArray&, int moveSide);
void uctBackPropagation(UCTNode* node, double value);
UCTNode* uctExpand(UCTNode* node);
UctRes  uctAll(const boardArray& board, const queenArray&, int moveSide, double calTime = 1.0, bool isDisplayInfo = false);
void InitializeRandomSeed();

///////////////////////////////////////////////////具体实现
void initBoard(boardArray& board) {
    for (int i = 0; i < BOARD_SIZE; i++) {
        for (int j = 0; j < BOARD_SIZE; j++) {
            board[i][j] = EMPTY;
        }
    }
    //放置蓝方皇后
    board[0][3] = BLUE_QUEEN;
    board[0][6] = BLUE_QUEEN;
    board[3][0] = BLUE_QUEEN;
    board[3][9] = BLUE_QUEEN;

    //放置红方皇后
    board[6][0] = RED_QUEEN;
    board[6][9] = RED_QUEEN;
    board[9][3] = RED_QUEEN;
    board[9][6] = RED_QUEEN;
}

void initQueenPos(queenArray& queenPos) {
    //初始化蓝方皇后位置
    queenPos[1][0] = 3;
    queenPos[1][1] = 6;
    queenPos[1][2] = 30;
    queenPos[1][3] = 39;

    //初始化红方皇后位置
    queenPos[0][0] = 60;
    queenPos[0][1] = 69;
    queenPos[0][2] = 93;
    queenPos[0][3] = 96;
}

//控制台显示棋盘
void displayBoard(const boardArray& board)
{
    //打印行号
    std::cout << "\n\n   ";
    for (int i = 0; i < BOARD_SIZE; i++)
    {
        std::cout << i << "  ";
    }
    std::cout << std::endl << std::endl;

    //循环打印
    for (int i = 0; i < BOARD_SIZE; i++)
    {
        std::cout << i << "  "; //打印列号
        for (int j = 0; j < BOARD_SIZE; j++)
        {
            switch (board[i][j])
            {
            case EMPTY:
                std::cout << "_  ";
                break;
            case RED_QUEEN:
                std::cout << "R  ";
                break;
            case BLUE_QUEEN:
                std::cout << "B  ";
                break;
            case STONE:
                std::cout << "S  ";
                break;
            default:
                std::cout << "?  ";
                break;
            }
        }
        std::cout << std::endl << std::endl;
    }
}

void updateQueenPos(queenArray& queenPos, int moveSide, int from, int to) {
    //根据moveSide找到对应的皇后位置数组索引
    int sideIndex = (moveSide == RED_SIDE) ? 0 : 1;

    //找到from位置对应的皇后索引
    for (int i = 0; i < 4; ++i) {
        if (queenPos[sideIndex][i] == from) {
            queenPos[sideIndex][i] = to;
            break;
        }
    }
}

//是否获胜
bool isWin(const boardArray& board, queenArray& queenPos, int moveSide)
{
    int offset = moveSide == RED_SIDE ? 1 : 0;//判断反方

    for (int i = 0; i < 4; i++)
    {
        if (isNeighborsHaveEmpty(board, queenPos[offset][i]) == true)
        {
            return false;
        }
    }
    return true;
}

bool isNeighborsHaveEmpty(const boardArray& board, int actionFrom) {
    int fromX = actionFrom / BOARD_SIZE;
    int fromY = actionFrom % BOARD_SIZE;

    // 遍历邻居
    for (int i = 0; i < 8; ++i) {
        int toX = fromX + dx[i];
        int toY = fromY + dy[i];

        // 检查坐标是否越界
        if (toX >= 0 && toX < BOARD_SIZE && toY >= 0 && toY < BOARD_SIZE && board[toX][toY] == EMPTY) {
            return true; // 如果有一个空位置，就返回true
        }
    }

    return false; // 如果没有空位置，就返回false
}

std::vector<int> getExpandTerritory(const boardArray& board, int actionFrom) {
    std::vector<int> expandPos;

    int fromX = actionFrom / BOARD_SIZE;
    int fromY = actionFrom % BOARD_SIZE;

    // 检查所有方向的扩展
    for (int i = 0; i < 8; i++) {
        int x = fromX + dx[i];
        int y = fromY + dy[i];

        while (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY) {
            expandPos.push_back(x * BOARD_SIZE + y);
            x += dx[i];
            y += dy[i];
        }
    }

    return expandPos;
}

std::vector<MoveAction> getOneQueenMove(const boardArray& board, int actionFrom) {
    std::vector<MoveAction> moves;
    std::vector<int> expandPositions = getExpandTerritory(board, actionFrom);

    // 为每个扩展位置生成移动动作
    for (int expandPos : expandPositions) {
        std::vector<int> stonePositions = getExpandTerritory(board, expandPos);

        for (int stonePos : stonePositions) {
            MoveAction action;
            action.From = actionFrom;
            action.To = expandPos;
            action.Stone = stonePos;
            moves.push_back(action);
        }
    }

    return moves;
}

std::vector<MoveAction> getSideQueenOneMoveAction(const boardArray& board, const queenArray& queenPos, int moveSide) {
    std::vector<MoveAction> vecGetMovePos;
    int offset = moveSide == RED_SIDE ? 0 : 1;
    int tempChess = moveSide == RED_SIDE ? RED_QUEEN : BLUE_QUEEN;


    for (int k = 0; k < 4; k++)
    {
        int fromX = queenPos[offset][k] / BOARD_SIZE;
        int fromY = queenPos[offset][k] % BOARD_SIZE;


        for (int i = 0; i < 8; i++) {
            int x = fromX + dx[i];
            int y = fromY + dy[i];

            while (isLegalArr[x+1][y+1] && board[x][y] == EMPTY) {
                vecGetMovePos.push_back({queenPos[offset][k],x * BOARD_SIZE + y,-1});

                x += dx[i];
                y += dy[i];
            }
        }
    }

    return vecGetMovePos;
}

std::vector<MoveValue> getSideQueenMoveAction(boardArray& board,const queenArray& queenPos, int moveSide)
{
    std::vector<MoveValue> vecGetMovePos;
    int offset = moveSide == RED_SIDE ? 0 : 1;
    int tempChess = moveSide == RED_SIDE ? RED_QUEEN : BLUE_QUEEN;


    for (int k = 0; k < 4; k++)
    {
        int fromX = queenPos[offset][k] / BOARD_SIZE;
        int fromY = queenPos[offset][k] % BOARD_SIZE;
        //让当前皇后为空
        board[fromX][fromY] = EMPTY;
        //int tempQueenPos = queenPos[offset][k];

        for (int i = 0; i < 8; i++) {
            int x = fromX + dx[i];
            int y = fromY + dy[i];

            while (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY) {//x >= 0 && x < BOARD_SIZE  && y >= 0 && y < BOARD_SIZE
                // board[x][y] = tempChess;////
                 //updateQueenPos(queenPos, moveSide, queenPos[offset][k], x * BOARD_SIZE + y);////
                 //放障碍
                for (int j = 0; j < 8; j++) {
                    int stoneX = x + dx[j];
                    int stoneY = y + dy[j];


                    while (isLegalArr[stoneX + 1][stoneY + 1] && board[stoneX][stoneY] == EMPTY) {
                        //board[stoneX][stoneY] = STONE;//
                        vecGetMovePos.push_back({ {queenPos[offset][k],x * BOARD_SIZE + y,stoneX * BOARD_SIZE + stoneY},0.0,0.0,0.0 });
                        //vecGetMovePos.push_back({ {tempQueenPos,x * BOARD_SIZE + y,stoneX * BOARD_SIZE + stoneY},valueT1(board,queenPos,moveSide) });
                        //
                        board[stoneX][stoneY] = EMPTY;//
                        stoneX += dx[j];
                        stoneY += dy[j];
                    }
                }
                //board[x][y] = EMPTY;////
                //updateQueenPos(queenPos, moveSide, x * BOARD_SIZE + y ,queenPos[offset][k]);////
                x += dx[i];
                y += dy[i];
            }
        }
        board[fromX][fromY] = tempChess;
    }

    return vecGetMovePos;
}

#if GEN217_POLICY_SHORTLIST
struct RankedPolicyPosition {
    int position;
    double logProbability;
};

static void evaluateGen217Policy(
    const boardArray& board,
    int moveSide,
    int stage,
    int marker,
    float* logits)
{
    float inputs[gen217_policy::INPUT_SIZE] = {0.0f};
    int currentQueen = moveSide == RED_SIDE ? RED_QUEEN : BLUE_QUEEN;
    int opponentQueen = moveSide == RED_SIDE ? BLUE_QUEEN : RED_QUEEN;
    for (int position = 0; position < BOARD_GRID_SIZE; position++) {
        int piece = board[position / BOARD_SIZE][position % BOARD_SIZE];
        if (piece == currentQueen)
            inputs[position] = 1.0f;
        else if (piece == opponentQueen)
            inputs[BOARD_GRID_SIZE + position] = 1.0f;
        else if (piece == STONE)
            inputs[2 * BOARD_GRID_SIZE + position] = 1.0f;
    }
    if (stage == 1 && marker >= 0)
        inputs[3 * BOARD_GRID_SIZE + marker] = 1.0f;
    else if (stage == 2 && marker >= 0)
        inputs[4 * BOARD_GRID_SIZE + marker] = 1.0f;
    inputs[5 * BOARD_GRID_SIZE + stage] = 1.0f;

    float hidden1[gen217_policy::HIDDEN_SIZE];
    float hidden2[gen217_policy::HIDDEN_SIZE];
    for (int output = 0; output < gen217_policy::HIDDEN_SIZE; output++) {
        float value = gen217_policy::HIDDEN1_BIAS[output];
        const float* weights = gen217_policy::HIDDEN1_WEIGHTS
            + output * gen217_policy::INPUT_SIZE;
        for (int input = 0; input < gen217_policy::INPUT_SIZE; input++)
            value += weights[input] * inputs[input];
        hidden1[output] = std::max(value, 0.0f);
    }
    for (int output = 0; output < gen217_policy::HIDDEN_SIZE; output++) {
        float value = gen217_policy::HIDDEN2_BIAS[output];
        const float* weights = gen217_policy::HIDDEN2_WEIGHTS
            + output * gen217_policy::HIDDEN_SIZE;
        for (int input = 0; input < gen217_policy::HIDDEN_SIZE; input++)
            value += weights[input] * hidden1[input];
        hidden2[output] = std::max(value, 0.0f);
    }
    int headOffset = stage * gen217_policy::POLICY_SIZE;
    for (int output = 0; output < gen217_policy::POLICY_SIZE; output++) {
        float value = gen217_policy::OUTPUT_BIAS[headOffset + output];
        const float* weights = gen217_policy::OUTPUT_WEIGHTS
            + (headOffset + output) * gen217_policy::HIDDEN_SIZE;
        for (int input = 0; input < gen217_policy::HIDDEN_SIZE; input++)
            value += weights[input] * hidden2[input];
        logits[output] = value;
    }
}

static std::vector<RankedPolicyPosition> rankPolicyPositions(
    const std::vector<int>& legalPositions,
    const float* logits,
    int width)
{
    std::vector<RankedPolicyPosition> ranked;
    if (legalPositions.empty())
        return ranked;
    float maxLogit = logits[legalPositions[0]];
    for (int position : legalPositions)
        maxLogit = std::max(maxLogit, logits[position]);
    double probabilitySum = 0.0;
    for (int position : legalPositions)
        probabilitySum += exp((double)logits[position] - maxLogit);
    double logNormalizer = (double)maxLogit + log(probabilitySum);
    ranked.reserve(legalPositions.size());
    for (int position : legalPositions)
        ranked.push_back({position, (double)logits[position] - logNormalizer});
    std::sort(
        ranked.begin(), ranked.end(),
        [](const RankedPolicyPosition& left, const RankedPolicyPosition& right) {
            return left.logProbability > right.logProbability;
        }
    );
    if ((int)ranked.size() > width)
        ranked.resize(width);
    return ranked;
}

std::vector<MoveValue> getSideQueenPolicyMoveAction(
    const boardArray& board,
    const queenArray& queenPos,
    int moveSide)
{
    std::vector<MoveValue> moves;
    int offset = moveSide == RED_SIDE ? 0 : 1;
    std::vector<int> legalQueens;
    for (int queenIndex = 0; queenIndex < 4; queenIndex++) {
        int from = queenPos[offset][queenIndex];
        if (!getExpandTerritory(board, from).empty())
            legalQueens.push_back(from);
    }
    float stage0Logits[BOARD_GRID_SIZE];
    evaluateGen217Policy(board, moveSide, 0, -1, stage0Logits);
    std::vector<RankedPolicyPosition> rankedQueens = rankPolicyPositions(
        legalQueens, stage0Logits, (int)legalQueens.size());

    for (const RankedPolicyPosition& queen : rankedQueens) {
        float stage1Logits[BOARD_GRID_SIZE];
        evaluateGen217Policy(board, moveSide, 1, queen.position, stage1Logits);
        std::vector<int> legalDestinations = getExpandTerritory(board, queen.position);
        std::vector<RankedPolicyPosition> rankedDestinations = rankPolicyPositions(
            legalDestinations, stage1Logits, GEN217_POLICY_TO_WIDTH);

        for (const RankedPolicyPosition& destination : rankedDestinations) {
            boardArray movedBoard;
            memcpy(movedBoard, board, sizeof(int) * BOARD_GRID_SIZE);
            movedBoard[destination.position / BOARD_SIZE][destination.position % BOARD_SIZE]
                = movedBoard[queen.position / BOARD_SIZE][queen.position % BOARD_SIZE];
            movedBoard[queen.position / BOARD_SIZE][queen.position % BOARD_SIZE] = EMPTY;

            float stage2Logits[BOARD_GRID_SIZE];
            evaluateGen217Policy(
                movedBoard, moveSide, 2, destination.position, stage2Logits);
            std::vector<int> legalArrows = getExpandTerritory(
                movedBoard, destination.position);
            std::vector<RankedPolicyPosition> rankedArrows = rankPolicyPositions(
                legalArrows, stage2Logits, GEN217_POLICY_ARROW_WIDTH);
            for (const RankedPolicyPosition& arrow : rankedArrows) {
                double logPrior = queen.logProbability
                    + destination.logProbability + arrow.logProbability;
                moves.push_back({
                    {queen.position, destination.position, arrow.position},
                    0.0,
                    logPrior,
                    0.0,
                });
            }
        }
    }

    if (moves.empty())
        return moves;
    double maxLogPrior = moves[0].prior;
    for (const MoveValue& move : moves)
        maxLogPrior = std::max(maxLogPrior, move.prior);
    double priorSum = 0.0;
    for (MoveValue& move : moves) {
        move.prior = exp(move.prior - maxLogPrior);
        priorSum += move.prior;
    }
    for (MoveValue& move : moves)
        move.prior /= priorSum;
    return moves;
}
#endif

std::vector<MoveValue> getSideQueenMoveValue(
    boardArray& board,
    const queenArray& queenPos,
    int moveSide,
    int searchDepth)
{
#if GEN217_POLICY_SHORTLIST
    std::vector<MoveValue> vecSideMoveValue =
        (GEN217_POLICY_FULL_ROOT && searchDepth == 0)
        ? getSideQueenMoveAction(board, queenPos, moveSide)
        : getSideQueenPolicyMoveAction(board, queenPos, moveSide);
    bool hasPolicyPrior = !(GEN217_POLICY_FULL_ROOT && searchDepth == 0);
#else
    std::vector<MoveValue> vecSideMoveValue = getSideQueenMoveAction(board, queenPos, moveSide);
#endif
    //int tempBoard[10][10];
    //memccpy(tempBoard,board,100*4);

    const int num_moves = vecSideMoveValue.size();
#if GEN217_POLICY_SHORTLIST
    double maxPolicyPrior = 0.0;
    if (hasPolicyPrior) {
        for (const MoveValue& move : vecSideMoveValue)
            maxPolicyPrior = std::max(maxPolicyPrior, move.prior);
    }
#endif

    // 预计算所有坐标
    struct MoveCoord {
        int fromX, fromY, toX, toY, stoneX, stoneY;
    };
    std::vector<MoveCoord> coords;
    coords.reserve(num_moves);

    for (const auto& move : vecSideMoveValue) {
        coords.push_back({
            move.action.From / BOARD_SIZE,
            move.action.From % BOARD_SIZE,
            move.action.To / BOARD_SIZE,
            move.action.To % BOARD_SIZE,
            move.action.Stone / BOARD_SIZE,
            move.action.Stone % BOARD_SIZE
            });
    }

    int max_threads = omp_get_num_procs();
    omp_set_num_threads(max_threads);
    #pragma omp parallel for shared(vecSideMoveValue)
    for (int i = 0; i < vecSideMoveValue.size(); i++)
    {
        //boardArray tempBoard = board;
        //queenArray tempQueenPos = queenPos;
        boardArray tempBoard;
        queenArray tempQueenPos;
        memcpy(tempBoard,board,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
        memcpy(tempQueenPos,queenPos,sizeof(int)*8);//复制当前红方皇后位置


        const auto& coord = coords[i];

        //下一步棋
        //tempBoard[vecSideMoveValue[i].action.To / BOARD_SIZE][vecSideMoveValue[i].action.To % BOARD_SIZE] = tempBoard[vecSideMoveValue[i].action.From / BOARD_SIZE][vecSideMoveValue[i].action.From % BOARD_SIZE];
        //tempBoard[vecSideMoveValue[i].action.From / BOARD_SIZE][vecSideMoveValue[i].action.From % BOARD_SIZE] = EMPTY;
        //tempBoard[vecSideMoveValue[i].action.Stone / BOARD_SIZE][vecSideMoveValue[i].action.Stone % BOARD_SIZE] = STONE;

        tempBoard[coord.toX][coord.toY] = tempBoard[coord.fromX][coord.fromY];
        tempBoard[coord.fromX][coord.fromY] = EMPTY;
        tempBoard[coord.stoneX][coord.stoneY] = STONE;

        //updateQueenPos(tempQueenPos,moveSide,vecSideMoveValue[i].action.From,vecSideMoveValue[i].action.To);
        updateQueenPos(tempQueenPos, moveSide, vecSideMoveValue[i].action.From, vecSideMoveValue[i].action.To);

        // The fitted model is trained from the actual player-to-move perspective.
        // A child is the opponent's turn, so negate that value for move ordering.
        vecSideMoveValue[i].value = -valueAll(tempBoard, tempQueenPos, -moveSide);
#if GEN217_POLICY_SHORTLIST
        // The prior is already normalized over shortlisted complete moves. A
        // bounded log-prior penalty breaks close value ties without turning a
        // policy score into a fictitious rollout result.
        if (hasPolicyPrior) {
            double relativeLogPrior = log(
                std::max(vecSideMoveValue[i].prior, 1.0e-12)
                / std::max(maxPolicyPrior, 1.0e-12));
            vecSideMoveValue[i].orderValue = vecSideMoveValue[i].value
                + GEN217_POLICY_ORDER_WEIGHT * std::max(relativeLogPrior / 8.0, -1.0);
        }
        else {
            vecSideMoveValue[i].prior = 0.0;
            vecSideMoveValue[i].orderValue = vecSideMoveValue[i].value;
        }
#else
        vecSideMoveValue[i].orderValue = vecSideMoveValue[i].value;
#endif


        //updateQueenPos(tempQueenPos,moveSide, vecSideMoveValue[i].action.To, vecSideMoveValue[i].action.From);

        //还原这步棋
        //(*tempBoard)[vecSideMoveValue[i].action.Stone] = EMPTY;
        //(*tempBoard)[vecSideMoveValue[i].action.From] = (*tempBoard)[vecSideMoveValue[i].action.To];
        //(*tempBoard)[vecSideMoveValue[i].action.To] = EMPTY;
    }

    return vecSideMoveValue;

}

void checkDisplayMoveValue(const std::vector<MoveValue>& vecMoveValue)
{
    for (int i = 0; i < vecMoveValue.size(); i++){
        printf("\n%4d. From:%2d  To:%2d  Stone:%2d Value:%f", i + 1, vecMoveValue[i].action.From, vecMoveValue[i].action.To, vecMoveValue[i].action.Stone, vecMoveValue[i].value);
    }
}

double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide, double* wValue)
{
    double value = 0;
    int tempRedDisBoard[BOARD_GRID_SIZE] = { 0 };
    int tempBlueDisBoard[BOARD_GRID_SIZE] = { 0 };
    std::queue<int> queueRed, queueBlue;

    for (int i = 0; i < 4; ++i) {
        queueRed.push(queenPos[0][i]);
        queueBlue.push(queenPos[1][i]);
    }

    // BFS实现
    auto bfs = [&](std::queue<int>& q, int* distBoard) {
        int d = 1;
        while (!q.empty()) {
            int size = q.size();
            for (int i = 0; i < size; ++i) {
                int pos = q.front();
                q.pop();
                int fromX = pos / BOARD_SIZE;
                int fromY = pos % BOARD_SIZE;
                for (int j = 0; j < 8; ++j) {
                    int x = fromX + dx[j];
                    int y = fromY + dy[j];
                    int newPos = x * BOARD_SIZE + y;
                    while (isLegalArr[x + 1][y + 1] && distBoard[newPos] >= d) {
                        if (distBoard[newPos] > d) {
                            distBoard[newPos] = d;
                            q.push(newPos);
                        }
                        x += dx[j];
                        y += dy[j];
                        newPos = x * BOARD_SIZE + y;
                    }
                }
            }
            ++d;
        }
        };

    int count = 0;
    for (int i = 0; i < BOARD_SIZE; ++i)
    {
        for (int j = 0; j < BOARD_SIZE; ++j)
        {
            if (board[i][j] == EMPTY)
            {
                tempRedDisBoard[count] = INT_MAX;
                tempBlueDisBoard[count] = INT_MAX;
                count++; continue;
            }
            else {
                count++;
            }
        }
    }

    bfs(queueRed, tempRedDisBoard);
    bfs(queueBlue, tempBlueDisBoard);

    double w = 0;
    for (int i = 0; i < BOARD_GRID_SIZE; ++i) {
        if (tempRedDisBoard[i] < tempBlueDisBoard[i]) {
            value += 1;
        }
        else if (tempRedDisBoard[i] > tempBlueDisBoard[i]) {
            value -= 1;
        }

        // w is a phase/contested-reachability feature. Occupied cells retain
        // distance zero in both arrays and used to add a spurious 1.0 each.
        // Fit and evaluate only on empty cells.
        if (board[i / BOARD_SIZE][i % BOARD_SIZE] != EMPTY ||
            tempRedDisBoard[i] == INT_MAX || tempBlueDisBoard[i] == INT_MAX)
        {
            w += 0;
        }
        else
        {
            w += pow(2.0, -abs(tempRedDisBoard[i] - tempBlueDisBoard[i]));
        }
    }
    *wValue = w;
    return moveSide == RED_SIDE ? value : -value;
}

double valueT1(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    double w;
    return valueT1(board, queenPos, moveSide, &w);
}


double valueT2(const boardArray& board,const queenArray& queenPos, int moveSide)
{
    double value = 0;
    int tempRedDisBoard[BOARD_GRID_SIZE] = { 0 };
    int tempBlueDisBoard[BOARD_GRID_SIZE] = { 0 };
    std::queue<int> queueRed, queueBlue;

    for (int i = 0; i < 4; ++i) {
        queueRed.push(queenPos[0][i]);
        queueBlue.push(queenPos[1][i]);
    }

    auto bfs = [&](std::queue<int>& q, int* distBoard) {
        int d = 1;
        while (!q.empty()) {
            int size = q.size();
            for (int i = 0; i < size; ++i) {
                int pos = q.front();
                q.pop();
                int fromX = pos / BOARD_SIZE;
                int fromY = pos % BOARD_SIZE;
                for (int j = 0; j < 8; ++j) {
                    int x = fromX + dx[j];
                    int y = fromY + dy[j];
                    int newPos = x * BOARD_SIZE + y;

                    if (isLegalArr[x + 1][y + 1] && distBoard[newPos] >= d) {
                        if (distBoard[newPos] > d) {
                            distBoard[newPos] = d;
                            q.push(newPos);
                        }
                    }
                }
            }
            ++d;
        }
        };

    int count = 0;
    for (int i = 0; i < BOARD_SIZE; ++i)
    {
        for (int j = 0; j < BOARD_SIZE; ++j)
        {
            if (board[i][j] == EMPTY)
            {
                tempRedDisBoard[count] = INT_MAX;
                tempBlueDisBoard[count] = INT_MAX;
                count++; continue;
            }
            else {
                count++;
            }
        }
    }

    bfs(queueRed, tempRedDisBoard);
    bfs(queueBlue, tempBlueDisBoard);

    for (int i = 0; i < BOARD_GRID_SIZE; ++i) {
        if (tempRedDisBoard[i] < tempBlueDisBoard[i]) {
            value += 1;
        }
        else if (tempRedDisBoard[i] > tempBlueDisBoard[i]) {
            value -= 1;
        }
    }

    return moveSide == RED_SIDE ? value : -value;
}




double calculateOneQueenMobilityValue(const boardArray& board, int kingPosX, int kingPosY)
{
    int count;
    int N;
    int maxCount = 3;
    double mobilityValue = 0;
    //正左
    count = 1;
    while ((kingPosY - count) >= 0 && board[kingPosX][kingPosY - count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, kingPosX, (kingPosY - count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //左上

    count = 1;
    while ((kingPosX - count) >= 0 && (kingPosY - count) >= 0 && board[kingPosX - count][kingPosY - count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX - count), (kingPosY - count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //正上
    count = 1;
    while ((kingPosX - count) >= 0 && board[kingPosX - count][kingPosY] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX - count), kingPosY);
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //右上
    count = 1;
    while ((kingPosX - count) >= 0 && (kingPosY + count) <= 9 && board[kingPosX - count][kingPosY + count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX - count), (kingPosY + count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //正右
    count = 1;
    while ((kingPosY + count) <= 9 && board[kingPosX][kingPosY + count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, kingPosX, (kingPosY + count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //右下
    count = 1;
    while ((kingPosX + count) <= 9 && (kingPosY + count) <= 9 && board[kingPosX + count][kingPosY + count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX + count), (kingPosY + count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //正下
    count = 1;

    while ((kingPosX + count) <= 9 && board[kingPosX + count][kingPosY] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX + count), kingPosY);
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }


    //左下
    count = 1;

    while ((kingPosX + count) <= 9 && (kingPosY - count) >= 0 && board[kingPosX + count][kingPosY - count] == EMPTY)
    {
        N = getNeighborsEmptyNumber(board, (kingPosX + count), (kingPosY - count));
        mobilityValue += N * pow(2, 1 - count);
        count++;

        if (count >= maxCount)
        {
            break;
        }
    }

    return mobilityValue;
}

double valueMobility(const boardArray& board,const queenArray& queenPos, int moveSide) {
    double valueMRed[4] = { 0 }, valueMBlue[4] = { 0 };


    for (int i = 0; i < 4; i++) {
        int kingPosX = queenPos[0][i] / BOARD_SIZE;
        int kingPosY = queenPos[0][i] % BOARD_SIZE;
        valueMRed[i] = calculateOneQueenMobilityValue(board, kingPosX, kingPosY);
    }

    for (int i = 0; i < 4; i++) {
        int kingPosX = queenPos[1][i] / BOARD_SIZE;
        int kingPosY = queenPos[1][i] % BOARD_SIZE;
        valueMBlue[i] = calculateOneQueenMobilityValue(board, kingPosX, kingPosY);
    }

    double mobilityValue = 0;

    for (int i = 0; i < 4; i++) {
        if (valueMBlue[i] <= 5) {
            mobilityValue += -0.4 * valueMBlue[i] + 7;
        }
        else {
            mobilityValue += 85.0 / (12 + valueMBlue[i]);
        }
        if (valueMRed[i] <= 5) {
            mobilityValue -= -0.4 * valueMRed[i] + 7;
        }
        else {
            mobilityValue -= 85.0 / (12 + valueMRed[i]);
        }
    }

    return (moveSide == RED_SIDE) ? mobilityValue : -mobilityValue;
}

// 获得某一点周围一圈邻接为空的个数
int getNeighborsEmptyNumber(const boardArray& board, int actionFrom)
{
    int count = 0;

    int fromX = actionFrom / BOARD_SIZE;
    int fromY = actionFrom % BOARD_SIZE;
    for (int i = 0; i < 8; ++i) {
        int x = fromX + dx[i];
        int y = fromY + dy[i];
        if (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY)
        {
            count++;
        }
    }
    return count;
}

// 获得某一点周围一圈邻接为空的个数
int getNeighborsEmptyNumber(const boardArray& board, int fromX, int fromY)
{
    int count = 0;

    for (int i = 0; i < 8; ++i) {
        int x = fromX + dx[i];
        int y = fromY + dy[i];
        if (isLegalArr[x + 1][y + 1] && board[x][y] == EMPTY)
        {
            count++;
        }
    }
    return count;
}

struct AreaStructureFeatures {
    double activeQueens = 0.0;
    double exclusiveQueenRedundancy = 0.0;
    double activeAreaCount = 0.0;
    double blockerQueens = 0.0;
    double blockerSwing = 0.0;
    double gatewayControl = 0.0;
    double territoryDeadEndRisk = 0.0;
    double territoryCutRisk = 0.0;
};

AreaStructureFeatures calculateAreaStructureFeatures(
    const boardArray& board, const int (&queenDistance)[2][BOARD_GRID_SIZE])
{
    AreaStructureFeatures result;
#if VALUE_FEATURE_AREAS || VALUE_FEATURE_GATES || VALUE_FEATURE_ENDGAME
    bool traversable[BOARD_GRID_SIZE] = {};
    bool empty[BOARD_GRID_SIZE] = {};
    int component[BOARD_GRID_SIZE];
    std::fill(component, component + BOARD_GRID_SIZE, -1);
    std::vector<std::vector<int>> componentNodes;
    std::vector<int> componentEmpty;
    std::vector<int> componentRed;
    std::vector<int> componentBlue;

    for (int position = 0; position < BOARD_GRID_SIZE; ++position) {
        int row = position / BOARD_SIZE;
        int column = position % BOARD_SIZE;
        traversable[position] = board[row][column] != STONE;
        empty[position] = board[row][column] == EMPTY;
    }

    for (int start = 0; start < BOARD_GRID_SIZE; ++start) {
        if (!traversable[start] || component[start] >= 0) continue;
        int componentId = static_cast<int>(componentNodes.size());
        componentNodes.push_back({});
        componentEmpty.push_back(0);
        componentRed.push_back(0);
        componentBlue.push_back(0);
        std::queue<int> pending;
        pending.push(start);
        component[start] = componentId;
        while (!pending.empty()) {
            int position = pending.front();
            pending.pop();
            componentNodes[componentId].push_back(position);
            int row = position / BOARD_SIZE;
            int column = position % BOARD_SIZE;
            if (board[row][column] == EMPTY) ++componentEmpty[componentId];
            else if (board[row][column] == RED_QUEEN) ++componentRed[componentId];
            else if (board[row][column] == BLUE_QUEEN) ++componentBlue[componentId];
            for (int direction = 0; direction < 8; ++direction) {
                int nextRow = row + dx[direction];
                int nextColumn = column + dy[direction];
                if (!isLegalArr[nextRow + 1][nextColumn + 1]) continue;
                int next = nextRow * BOARD_SIZE + nextColumn;
                if (traversable[next] && component[next] < 0) {
                    component[next] = componentId;
                    pending.push(next);
                }
            }
        }
    }

    double cutSwing[BOARD_GRID_SIZE] = {};
#if VALUE_FEATURE_GATES || VALUE_FEATURE_ENDGAME
    int discovery[BOARD_GRID_SIZE];
    int low[BOARD_GRID_SIZE] = {};
    int parent[BOARD_GRID_SIZE];
    int subtreeEmpty[BOARD_GRID_SIZE] = {};
    std::fill(discovery, discovery + BOARD_GRID_SIZE, -1);
    std::fill(parent, parent + BOARD_GRID_SIZE, -1);
    int discoveryTime = 0;

    for (int componentId = 0;
         componentId < static_cast<int>(componentNodes.size());
         ++componentId) {
        if (componentNodes[componentId].empty()) continue;
        int totalEmpty = componentEmpty[componentId];
        std::function<void(int)> visit = [&](int position) {
            discovery[position] = discoveryTime;
            low[position] = discoveryTime;
            ++discoveryTime;
            subtreeEmpty[position] = empty[position] ? 1 : 0;
            std::vector<int> separatedParts;
            int row = position / BOARD_SIZE;
            int column = position % BOARD_SIZE;
            for (int direction = 0; direction < 8; ++direction) {
                int nextRow = row + dx[direction];
                int nextColumn = column + dy[direction];
                if (!isLegalArr[nextRow + 1][nextColumn + 1]) continue;
                int next = nextRow * BOARD_SIZE + nextColumn;
                if (!traversable[next]) continue;
                if (discovery[next] < 0) {
                    parent[next] = position;
                    visit(next);
                    subtreeEmpty[position] += subtreeEmpty[next];
                    low[position] = std::min(low[position], low[next]);
                    if (low[next] >= discovery[position]) {
                        separatedParts.push_back(subtreeEmpty[next]);
                    }
                }
                else if (next != parent[position]) {
                    low[position] = std::min(low[position], discovery[next]);
                }
            }

            int separatedSum = 0;
            int largestPart = 0;
            int positiveParts = 0;
            for (int part : separatedParts) {
                separatedSum += part;
                if (part > 0) {
                    largestPart = std::max(largestPart, part);
                    ++positiveParts;
                }
            }
            int remainder = totalEmpty - (empty[position] ? 1 : 0) - separatedSum;
            if (remainder > 0) {
                largestPart = std::max(largestPart, remainder);
                ++positiveParts;
            }
            int totalAfterRemoval = totalEmpty - (empty[position] ? 1 : 0);
            if (positiveParts >= 2) {
                cutSwing[position] = totalAfterRemoval - largestPart;
            }
        };
        visit(componentNodes[componentId].front());
    }
#endif

    double redDeadEndRisk = 0.0;
    double blueDeadEndRisk = 0.0;
    double redCutRisk = 0.0;
    double blueCutRisk = 0.0;
    for (int componentId = 0;
         componentId < static_cast<int>(componentNodes.size());
         ++componentId) {
        int redCount = componentRed[componentId];
        int blueCount = componentBlue[componentId];
        int emptyCount = componentEmpty[componentId];
        if (emptyCount == 0) continue;
        if (redCount > 0 && blueCount > 0) {
#if VALUE_FEATURE_AREAS
            result.activeAreaCount += 1.0;
            result.activeQueens += redCount - blueCount;
#endif
            continue;
        }
        if (redCount == 0 && blueCount == 0) continue;
#if VALUE_FEATURE_AREAS
        if (redCount > 0) result.exclusiveQueenRedundancy -= std::max(0, redCount - 1);
        else result.exclusiveQueenRedundancy += std::max(0, blueCount - 1);
#endif
#if VALUE_FEATURE_ENDGAME
        int ownerCount = redCount > 0 ? redCount : blueCount;
        int deadEnds = 0;
        double areaCutRisk = 0.0;
        for (int position : componentNodes[componentId]) {
            if (!empty[position]) continue;
            int row = position / BOARD_SIZE;
            int column = position % BOARD_SIZE;
            int degree = 0;
            for (int direction = 0; direction < 8; ++direction) {
                int nextRow = row + dx[direction];
                int nextColumn = column + dy[direction];
                if (!isLegalArr[nextRow + 1][nextColumn + 1]) continue;
                int next = nextRow * BOARD_SIZE + nextColumn;
                if (traversable[next]) ++degree;
            }
            if (degree <= 1) ++deadEnds;
            areaCutRisk += cutSwing[position];
        }
        double deadEndRisk = std::max(0, deadEnds - ownerCount);
        if (redCount > 0) {
            redDeadEndRisk += deadEndRisk;
            redCutRisk += areaCutRisk;
        }
        else {
            blueDeadEndRisk += deadEndRisk;
            blueCutRisk += areaCutRisk;
        }
#endif
    }

#if VALUE_FEATURE_GATES
    for (int position = 0; position < BOARD_GRID_SIZE; ++position) {
        int row = position / BOARD_SIZE;
        int column = position % BOARD_SIZE;
        if (board[row][column] == RED_QUEEN && cutSwing[position] > 0.0) {
            result.blockerQueens += 1.0;
            result.blockerSwing += cutSwing[position];
        }
        else if (board[row][column] == BLUE_QUEEN && cutSwing[position] > 0.0) {
            result.blockerQueens -= 1.0;
            result.blockerSwing -= cutSwing[position];
        }
        else if (board[row][column] == EMPTY && cutSwing[position] > 0.0) {
            int redDistance = queenDistance[0][position];
            int blueDistance = queenDistance[1][position];
            if (redDistance < 127 && blueDistance < 127) {
                if (redDistance < blueDistance) result.gatewayControl += cutSwing[position];
                else if (blueDistance < redDistance) result.gatewayControl -= cutSwing[position];
            }
        }
    }
#endif
#if VALUE_FEATURE_ENDGAME
    result.territoryDeadEndRisk = blueDeadEndRisk - redDeadEndRisk;
    result.territoryCutRisk = blueCutRisk - redCutRisk;
#endif
#endif
    return result;
}

void calculateSingleQueenDistances(
    const boardArray& board, int source, int (&distances)[BOARD_GRID_SIZE])
{
    static const int INF = 127;
    std::fill(distances, distances + BOARD_GRID_SIZE, INF);
    std::queue<int> pending;
    distances[source] = 0;
    pending.push(source);
    while (!pending.empty()) {
        int position = pending.front();
        pending.pop();
        int row = position / BOARD_SIZE;
        int column = position % BOARD_SIZE;
        int nextDistance = distances[position] + 1;
        for (int direction = 0; direction < 8; ++direction) {
            int nextRow = row + dx[direction];
            int nextColumn = column + dy[direction];
            while (
                isLegalArr[nextRow + 1][nextColumn + 1]
                && board[nextRow][nextColumn] == EMPTY
            ) {
                int nextPosition = nextRow * BOARD_SIZE + nextColumn;
                if (distances[nextPosition] > nextDistance) {
                    distances[nextPosition] = nextDistance;
                    pending.push(nextPosition);
                }
                nextRow += dx[direction];
                nextColumn += dy[direction];
            }
        }
    }
}

std::array<double, EVALUATION_FEATURE_COUNT> calculateEvaluationFeatures(
    const boardArray& board, const queenArray& queenPos, int moveSide)
{
    static const int INF = 127;
    int queenDistance[2][BOARD_GRID_SIZE];
    int kingDistance[2][BOARD_GRID_SIZE];

    for (int side = 0; side < 2; ++side) {
        std::fill(queenDistance[side], queenDistance[side] + BOARD_GRID_SIZE, INF);
        std::fill(kingDistance[side], kingDistance[side] + BOARD_GRID_SIZE, INF);
        std::queue<int> queenQueue;
        std::queue<int> kingQueue;
        for (int queen = 0; queen < 4; ++queen) {
            int position = queenPos[side][queen];
            queenDistance[side][position] = 0;
            kingDistance[side][position] = 0;
            queenQueue.push(position);
            kingQueue.push(position);
        }

        while (!queenQueue.empty()) {
            int position = queenQueue.front();
            queenQueue.pop();
            int row = position / BOARD_SIZE;
            int column = position % BOARD_SIZE;
            int nextDistance = queenDistance[side][position] + 1;
            for (int direction = 0; direction < 8; ++direction) {
                int nextRow = row + dx[direction];
                int nextColumn = column + dy[direction];
                while (
                    isLegalArr[nextRow + 1][nextColumn + 1]
                    && board[nextRow][nextColumn] == EMPTY
                ) {
                    int nextPosition = nextRow * BOARD_SIZE + nextColumn;
                    if (queenDistance[side][nextPosition] > nextDistance) {
                        queenDistance[side][nextPosition] = nextDistance;
                        queenQueue.push(nextPosition);
                    }
                    nextRow += dx[direction];
                    nextColumn += dy[direction];
                }
            }
        }

        while (!kingQueue.empty()) {
            int position = kingQueue.front();
            kingQueue.pop();
            int row = position / BOARD_SIZE;
            int column = position % BOARD_SIZE;
            int nextDistance = kingDistance[side][position] + 1;
            for (int direction = 0; direction < 8; ++direction) {
                int nextRow = row + dx[direction];
                int nextColumn = column + dy[direction];
                if (
                    isLegalArr[nextRow + 1][nextColumn + 1]
                    && board[nextRow][nextColumn] == EMPTY
                ) {
                    int nextPosition = nextRow * BOARD_SIZE + nextColumn;
                    if (kingDistance[side][nextPosition] > nextDistance) {
                        kingDistance[side][nextPosition] = nextDistance;
                        kingQueue.push(nextPosition);
                    }
                }
            }
        }
    }

    double t1 = 0.0;
    double t2 = 0.0;
    double c1 = 0.0;
    double c2 = 0.0;
    double w = 0.0;
    double emptyCount = 0.0;
    double secureTerritory = 0.0;
    double contestedCount = 0.0;
    for (int position = 0; position < BOARD_GRID_SIZE; ++position) {
        int row = position / BOARD_SIZE;
        int column = position % BOARD_SIZE;
        if (board[row][column] != EMPTY) {
            continue;
        }
        emptyCount += 1.0;
        int redQueenDistance = queenDistance[0][position];
        int blueQueenDistance = queenDistance[1][position];
        bool redQueenReachable = redQueenDistance < INF;
        bool blueQueenReachable = blueQueenDistance < INF;
        if (redQueenDistance < blueQueenDistance) t1 += 1.0;
        else if (redQueenDistance > blueQueenDistance) t1 -= 1.0;
        if (redQueenReachable) c1 += std::exp2(-redQueenDistance);
        if (blueQueenReachable) c1 -= std::exp2(-blueQueenDistance);
        if (redQueenReachable && blueQueenReachable) {
            w += std::exp2(-std::abs(redQueenDistance - blueQueenDistance));
            contestedCount += 1.0;
        }
        else if (redQueenReachable) secureTerritory += 1.0;
        else if (blueQueenReachable) secureTerritory -= 1.0;

        int redKingDistance = kingDistance[0][position];
        int blueKingDistance = kingDistance[1][position];
        if (redKingDistance < blueKingDistance) t2 += 1.0;
        else if (redKingDistance > blueKingDistance) t2 -= 1.0;
        if (!(redKingDistance == INF && blueKingDistance == INF)) {
            double margin = (blueKingDistance - redKingDistance) / 6.0;
            c2 += std::max(-1.0, std::min(1.0, margin));
        }
    }

    double legacyMobility[2][4] = {};
    double directMobility[2][4] = {};
    double combatMobilityByQueen[2][4] = {};
    double liberties[2][4] = {};
    int reachCount[2][BOARD_GRID_SIZE] = {};
    for (int side = 0; side < 2; ++side) {
        for (int queen = 0; queen < 4; ++queen) {
            int position = queenPos[side][queen];
            int row = position / BOARD_SIZE;
            int column = position % BOARD_SIZE;
            liberties[side][queen] = getNeighborsEmptyNumber(board, row, column);
            for (int direction = 0; direction < 8; ++direction) {
                int distance = 1;
                int nextRow = row + dx[direction];
                int nextColumn = column + dy[direction];
                while (
                    isLegalArr[nextRow + 1][nextColumn + 1]
                    && board[nextRow][nextColumn] == EMPTY
                ) {
                    int nextPosition = nextRow * BOARD_SIZE + nextColumn;
                    directMobility[side][queen] += 1.0;
                    reachCount[side][nextPosition] += 1;
                    if (distance <= 2
#if VALUE_FEATURE_COMBAT
                        || queenDistance[1 - side][nextPosition] < INF
#endif
                    ) {
                        double neighborCount = getNeighborsEmptyNumber(
                            board, nextRow, nextColumn);
                        if (distance <= 2) {
                            legacyMobility[side][queen] +=
                                neighborCount * std::exp2(1 - distance);
                        }
#if VALUE_FEATURE_COMBAT
                        if (queenDistance[1 - side][nextPosition] < INF) {
                            combatMobilityByQueen[side][queen] +=
                                neighborCount * std::exp2(-distance);
                        }
#endif
                    }
                    ++distance;
                    nextRow += dx[direction];
                    nextColumn += dy[direction];
                }
            }
        }
    }

    auto mobilityPenalty = [](double value) {
        return value <= 5.0 ? -0.4 * value + 7.0 : 85.0 / (12.0 + value);
    };
    auto standardDeviation = [](const double values[4]) {
        double mean = 0.25 * (values[0] + values[1] + values[2] + values[3]);
        double variance = 0.0;
        for (int i = 0; i < 4; ++i) {
            double difference = values[i] - mean;
            variance += difference * difference;
        }
        return std::sqrt(0.25 * variance);
    };

    double mobility = 0.0;
    double combatMobility = 0.0;
    double queenMobility = 0.0;
    double libertyDifference = 0.0;
    double trappedQueens = 0.0;
    for (int queen = 0; queen < 4; ++queen) {
        mobility += mobilityPenalty(legacyMobility[1][queen]);
        mobility -= mobilityPenalty(legacyMobility[0][queen]);
        queenMobility += directMobility[0][queen] - directMobility[1][queen];
        libertyDifference += liberties[0][queen] - liberties[1][queen];
        if (liberties[1][queen] <= 2.0) trappedQueens += 1.0;
        if (liberties[0][queen] <= 2.0) trappedQueens -= 1.0;
#if VALUE_FEATURE_COMBAT
        combatMobility += 30.0 / (5.0 + combatMobilityByQueen[1][queen]);
        combatMobility -= 30.0 / (5.0 + combatMobilityByQueen[0][queen]);
#endif
    }
    double weakestQueenMobility =
        *std::min_element(directMobility[0], directMobility[0] + 4)
        - *std::min_element(directMobility[1], directMobility[1] + 4);
    double queenMobilityBalance = standardDeviation(directMobility[1])
        - standardDeviation(directMobility[0]);
    double weakestLiberties =
        *std::min_element(liberties[0], liberties[0] + 4)
        - *std::min_element(liberties[1], liberties[1] + 4);
    double weakestCombatMobility = 0.0;
    double secondWeakestCombatMobility = 0.0;
    double strongestCombatMobility = 0.0;
    double combatMobilityBalance = 0.0;
    double combatActiveQueens = 0.0;
#if VALUE_FEATURE_COMBAT
    weakestCombatMobility =
        *std::min_element(combatMobilityByQueen[0], combatMobilityByQueen[0] + 4)
        - *std::min_element(combatMobilityByQueen[1], combatMobilityByQueen[1] + 4);
    double sortedCombatMobility[2][4];
    for (int side = 0; side < 2; ++side) {
        std::copy(
            combatMobilityByQueen[side],
            combatMobilityByQueen[side] + 4,
            sortedCombatMobility[side]);
        std::sort(sortedCombatMobility[side], sortedCombatMobility[side] + 4);
        for (int queen = 0; queen < 4; ++queen) {
            if (combatMobilityByQueen[side][queen] > 0.0) {
                combatActiveQueens += side == 0 ? 1.0 : -1.0;
            }
        }
    }
    secondWeakestCombatMobility =
        sortedCombatMobility[0][1] - sortedCombatMobility[1][1];
    strongestCombatMobility =
        sortedCombatMobility[0][3] - sortedCombatMobility[1][3];
    combatMobilityBalance = standardDeviation(combatMobilityByQueen[1])
        - standardDeviation(combatMobilityByQueen[0]);
#endif
    double reachOverlap = 0.0;
    for (int position = 0; position < BOARD_GRID_SIZE; ++position) {
        reachOverlap += std::max(reachCount[0][position] - 1, 0);
        reachOverlap -= std::max(reachCount[1][position] - 1, 0);
    }

    double centerControl = 0.0;
    double queenSpread = 0.0;
    for (int side = 0; side < 2; ++side) {
        double sideSign = side == 0 ? 1.0 : -1.0;
        for (int queen = 0; queen < 4; ++queen) {
            double row = queenPos[side][queen] / BOARD_SIZE;
            double column = queenPos[side][queen] % BOARD_SIZE;
            centerControl += sideSign * (
                4.5 - std::max(std::abs(row - 4.5), std::abs(column - 4.5)));
            for (int other = queen + 1; other < 4; ++other) {
                int otherRow = queenPos[side][other] / BOARD_SIZE;
                int otherColumn = queenPos[side][other] % BOARD_SIZE;
                queenSpread += sideSign * std::max(
                    std::abs(static_cast<int>(row) - otherRow),
                    std::abs(static_cast<int>(column) - otherColumn));
            }
        }
    }

    AreaStructureFeatures areaStructure =
        calculateAreaStructureFeatures(board, queenDistance);
    double queenLoadMin = 0.0;
    double queenLoadBalance = 0.0;
    double accessRedundancy = 0.0;
#if VALUE_FEATURE_ASSIGNMENT
    int individualQueenDistance[2][4][BOARD_GRID_SIZE];
    double queenLoad[2][4] = {};
    double sideRedundancy[2] = {};
    for (int side = 0; side < 2; ++side) {
        for (int queen = 0; queen < 4; ++queen) {
            calculateSingleQueenDistances(
                board, queenPos[side][queen], individualQueenDistance[side][queen]);
        }
    }
    for (int position = 0; position < BOARD_GRID_SIZE; ++position) {
        int row = position / BOARD_SIZE;
        int column = position % BOARD_SIZE;
        if (
            board[row][column] != EMPTY
            || queenDistance[0][position] >= INF
            || queenDistance[1][position] >= INF
        ) continue;
        for (int side = 0; side < 2; ++side) {
            int minimum = INF;
            for (int queen = 0; queen < 4; ++queen) {
                minimum = std::min(
                    minimum, individualQueenDistance[side][queen][position]);
            }
            int fastestCount = 0;
            for (int queen = 0; queen < 4; ++queen) {
                if (individualQueenDistance[side][queen][position] == minimum) {
                    ++fastestCount;
                }
            }
            if (minimum < INF && fastestCount > 0) {
                double share = 1.0 / fastestCount;
                for (int queen = 0; queen < 4; ++queen) {
                    if (individualQueenDistance[side][queen][position] == minimum) {
                        queenLoad[side][queen] += share;
                    }
                }
                sideRedundancy[side] += std::max(fastestCount - 1, 0);
            }
        }
    }
    queenLoadMin = *std::min_element(queenLoad[0], queenLoad[0] + 4)
        - *std::min_element(queenLoad[1], queenLoad[1] + 4);
    queenLoadBalance = standardDeviation(queenLoad[1])
        - standardDeviation(queenLoad[0]);
    accessRedundancy = sideRedundancy[0] - sideRedundancy[1];
#endif

    double perspective = moveSide == RED_SIDE ? 1.0 : -1.0;
    return {
        perspective * t1,
        perspective * t2,
        perspective * c1,
        perspective * c2,
        perspective * mobility,
        w,
        emptyCount,
        perspective * secureTerritory,
        contestedCount,
        perspective * queenMobility,
        perspective * weakestQueenMobility,
        perspective * queenMobilityBalance,
        perspective * libertyDifference,
        perspective * weakestLiberties,
        perspective * trappedQueens,
        perspective * reachOverlap,
        perspective * centerControl,
        perspective * queenSpread,
        perspective * combatMobility,
        perspective * weakestCombatMobility,
        perspective * areaStructure.activeQueens,
        perspective * areaStructure.exclusiveQueenRedundancy,
        areaStructure.activeAreaCount,
        perspective * areaStructure.blockerQueens,
        perspective * areaStructure.blockerSwing,
        perspective * areaStructure.gatewayControl,
        perspective * queenLoadMin,
        perspective * queenLoadBalance,
        perspective * accessRedundancy,
        perspective * areaStructure.territoryDeadEndRisk,
        perspective * areaStructure.territoryCutRisk,
        perspective * secondWeakestCombatMobility,
        perspective * strongestCombatMobility,
        perspective * combatMobilityBalance,
        perspective * combatActiveQueens,
    };
}

double evaluateFeatureArray(
    const std::array<double, EVALUATION_FEATURE_COUNT>& features)
{
    std::array<double, gen217_value_model::INPUT_SIZE> modelFeatures = {};
    static_assert(
        gen217_value_model::INPUT_SIZE <= EVALUATION_FEATURE_COUNT,
        "value model expects more inputs than the evaluator provides");
    for (int index = 0; index < gen217_value_model::INPUT_SIZE; ++index) {
        modelFeatures[index] = features[index];
    }
    double richValue = gen217_value_model::evaluate(modelFeatures);
#if GEN217_BLEND_PRODUCTION_RICH
    std::array<double, gen217_production_value_model::INPUT_SIZE>
        productionFeatures = {};
    static_assert(
        gen217_production_value_model::INPUT_SIZE <= EVALUATION_FEATURE_COUNT,
        "production value model expects too many inputs");
    for (
        int index = 0;
        index < gen217_production_value_model::INPUT_SIZE;
        ++index
    ) {
        productionFeatures[index] = features[index];
    }
    double productionRichValue =
        gen217_production_value_model::evaluate(productionFeatures);
    richValue = GEN217_NEW_RICH_WEIGHT * richValue
        + (1.0 - GEN217_NEW_RICH_WEIGHT) * productionRichValue;
#endif
    if (GEN217_LEGACY_BLEND <= 0.0) return richValue;
    std::array<double, 4> legacyFeatures = {
        features[0], features[1], features[4], features[5]
    };
    double legacyValue = gen217_legacy_value_model::evaluate(legacyFeatures);
#if GEN217_CALIBRATED_BLEND
    return gen217_value_blend::evaluate(richValue, legacyValue, features[5]);
#else
    return GEN217_LEGACY_BLEND * legacyValue
        + (1.0 - GEN217_LEGACY_BLEND) * richValue;
#endif
}

double valueAll(const boardArray& board, const queenArray& queenPos, int moveSide)
{
#if defined(AMAZON_AI_ORIGINAL_EVALUATOR) && AMAZON_AI_ORIGINAL_EVALUATOR
    // Keep the project's original four-feature/phase formula available as the
    // entry-level MCTS model.  The stronger module below uses the distilled
    // 18-feature evaluator instead.
    double w = 0;
    double t1 = valueT1(board, queenPos, moveSide, &w);
    double t2 = valueT2(board, queenPos, moveSide);
    double mobility = valueMobility(board, queenPos, moveSide);

    double k1, k2, k3;
    if (w >= 0 && w <= 14) {
        k1 = 1; k2 = 0; k3 = 0;
    }
    else if (w > 14 && w <= 25) {
        k1 = 1; k2 = 0; k3 = 0.2;
    }
    else if (w > 25 && w <= 40) {
        k1 = 1; k2 = 1; k3 = 1;
    }
    else if (w > 40 && w <= 55) {
        k1 = 1; k2 = 1; k3 = 2;
    }
    else if (w > 55 && w <= 63) {
        k1 = 1; k2 = 1; k3 = 3;
    }
    else {
        k1 = 1; k2 = 1; k3 = 4;
    }
    return t1 * k1 + t2 * k2 + k3 * mobility;
#else
    // Phase-dependent formula distilled from candidate_gen217 immediate MCTS
    // values on 288,915 complete-turn self-play positions. The fitted formula
    // and legacy gen217 evaluator are blended equally. See
    // src/ai/value_model_gen217.json.
    return evaluateFeatureArray(
        calculateEvaluationFeatures(board, queenPos, moveSide));
#endif
}



void deleteRoot(UCTNode* node)
{
    if (node == NULL)
    {
        return;
    }

    if (node->vecNodes.empty() != true)
    {
        for (int i = 0; i < node->vecNodes.size(); i++)
        {
            deleteRoot(node->vecNodes[i]);
        }
        delete(node);
    }
    else
    {

        delete(node);

    }
}

//初始化结点
UCTNode* uctInitNode(const boardArray& board, const queenArray& queenPos, UCTNode* head, int moveSide)
{
    head = new UCTNode;

    head->action.From = -1;
    head->action.To = -1;
    head->action.Stone = -1;

    head->message.side = -moveSide;
    head->message.value = -valueAll(board, queenPos, moveSide);
    head->message.r = 0;
    head->message.prior = 1.0;

    head->simulate.valueSum = 0.0;
    head->simulate.attempt = 0;
    //head->simulate.pro = 0;

    head->expandSize = 0;
    head->depth = 0;

    head->parent = NULL;

    //head->nodeBoard = board;
    //head->queenPos = queenPos;

    memcpy(head->nodeBoard,board,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
    memcpy(head->queenPos,queenPos,sizeof(int)*8);//复制当前红方皇后位置


    return head;
}

//UCT算法的选择
UCTNode* uctSelect(UCTNode* node)
{
    UCTNode* currentPtr = node;

    while (!currentPtr->vecNodes.empty()) {
        if (currentPtr->expandSize < currentPtr->maxSize && (currentPtr->simulate.attempt / 1000 + 1) * UCT_ADD_WIDTH + UCT_START_NUMBER > currentPtr->expandSize) {
            uctExpand(currentPtr);
        }

        UCTNode* bestNode = nullptr;
        double bestR = -1.1;

        for (int i = 0; i < currentPtr->vecNodes.size(); i++) {
            double tempR = uctGetR(currentPtr->vecNodes[i]);
            currentPtr->vecNodes[i]->message.r = tempR;

            if (tempR > bestR) {
                bestR = tempR;
                bestNode = currentPtr->vecNodes[i];
            }
        }

        currentPtr = bestNode;
    }

    return currentPtr;
}

//得到r值
double uctGetR(UCTNode* node)
{
    double meanValue = node->simulate.valueSum / node->simulate.attempt;
    double winProbability = 0.5 * (meanValue + 1.0);
#if GEN217_POLICY_PUCT
    double parentAttempts = std::max(node->parent->simulate.attempt, 1);
    return winProbability
        + 0.20 * (double)sqrt(
            (double)log(parentAttempts + 1.0) / node->simulate.attempt)
        + GEN217_POLICY_PUCT_WEIGHT * node->message.prior
            * sqrt(parentAttempts) / (1.0 + node->simulate.attempt);
#else
    return winProbability + 0.35 * (double)sqrt(
        (double)log(node->parent->simulate.attempt) / node->simulate.attempt);
#endif
}

//UCT算法的扩展
UCTNode* uctExpand(UCTNode* node)
{
    UCTNode* currentPtr = node;
    int moveSide = -currentPtr->message.side;

    bool isSideWin = isWin(currentPtr->nodeBoard,currentPtr->queenPos,currentPtr->message.side);

    if(isSideWin)
    {
        uctBackPropagation(currentPtr,1);
        return currentPtr;
    }

    std::vector<MoveValue> vecMoveValue;


    if(node->simulate.attempt < UCT_LEAF_SIMULATION_THRESHOLD && node->simulate.attempt > 0)
    {
        //从我方下棋开始且最后我方输棋
        double nextPlayerValue = uctSimulate(
            node->nodeBoard, node->queenPos, -node->message.side);
        uctBackPropagation(node, -nextPlayerValue);

        //OMPnRoundUCTSimulateSixStep(node,board,moveSide,4);

        return node;
    }

    /*if(node->depth == 8)
    {
        //从我方下棋开始且最后我方输棋
        if(uctSimulateSixStep(board,moveSide,6) == -moveSide)
        {
            uctBackPropagation(node,1);
        }
        else//从我方下棋开始且最后对方输棋
        {
            uctBackPropagation(node,-1);
        }

        return node;
    }*/


    int startNumber = node->expandSize;
    int endNumber;

    //节点是否为初始节点，只在扩展时模拟过一次
    if(node->vecMovePos.empty())
    {


        vecMoveValue = getSideQueenMoveValue(
            node->nodeBoard, node->queenPos, -node->message.side, node->depth);

        //uctNodeNumber += vecMoveValue.size();

        //uctVecNumber++;
//uctAllValueNumber += vecMoveValue.size();

        std::sort(vecMoveValue.begin(),vecMoveValue.end(),COMP());//按价值从大到小排序


        if(vecMoveValue.size() >= UCT_SELECT_NUMBER)
        {
            vecMoveValue.erase(vecMoveValue.begin()+UCT_SELECT_NUMBER ,vecMoveValue.end());
            node->maxSize = UCT_SELECT_NUMBER;
            //checkDisplayMoveValue(vecSideMoveValue);
        }
        else
        {
            node->maxSize = vecMoveValue.size();
        }

        node->vecMovePos = vecMoveValue;


        endNumber =  UCT_START_NUMBER >= node->maxSize ? node->maxSize : UCT_START_NUMBER;

        node->expandSize = endNumber;

    }
    else
    {
        vecMoveValue = node->vecMovePos;

        endNumber = (node->expandSize + UCT_ADD_WIDTH) >= node->maxSize ? node->maxSize : (node->expandSize + UCT_ADD_WIDTH);

        node->expandSize = endNumber;
    }

    //checkDisplayMoveValue(vecMoveValue);

    for (int i = startNumber; i < endNumber; i++)
    {
        UCTNode* newNode = new UCTNode;
        //uctNodeNumber++;
        //newNode->nodeBoard = node->nodeBoard;
        //newNode->queenPos = node->queenPos;
        memcpy(newNode->nodeBoard,node->nodeBoard,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
        memcpy(newNode->queenPos,node->queenPos,sizeof(int)*8);//复制当前红方皇后位置

        //移动皇后与放置障碍
        newNode->nodeBoard[vecMoveValue[i].action.To / BOARD_SIZE][vecMoveValue[i].action.To % BOARD_SIZE] = newNode->nodeBoard[vecMoveValue[i].action.From / BOARD_SIZE][vecMoveValue[i].action.From % BOARD_SIZE];
        newNode->nodeBoard[vecMoveValue[i].action.From / BOARD_SIZE][vecMoveValue[i].action.From % BOARD_SIZE] = EMPTY;
        newNode->nodeBoard[vecMoveValue[i].action.Stone / BOARD_SIZE][vecMoveValue[i].action.Stone % BOARD_SIZE] = STONE;

        //更新皇后位置
        updateQueenPos(newNode->queenPos, moveSide, vecMoveValue[i].action.From, vecMoveValue[i].action.To);

        newNode->action.From = vecMoveValue[i].action.From;
        newNode->action.To = vecMoveValue[i].action.To;
        newNode->action.Stone = vecMoveValue[i].action.Stone;
        newNode->parent = currentPtr;
        newNode->message.side = newNode->parent->message.side * -1;
        newNode->message.value = vecMoveValue[i].value;
        newNode->message.prior = vecMoveValue[i].prior;

        newNode->simulate.attempt = 0;
        newNode->simulate.valueSum = 0.0;
        newNode->message.r = -1;
        newNode->expandSize = 0;
        newNode->depth = newNode->parent->depth + 1;

        uctBackPropagation(newNode, newNode->message.value);


        node->vecNodes.push_back(newNode);
    }

    return currentPtr;
}


double uctSimulate(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    int randomIndex;
    int step;
    int tempSide = moveSide;

    std::vector<int> vecTemp;
    std::vector<MoveAction> vecMovePos;

    //boardArray temp_board = board;
    //queenArray temp_queenPos = queenPos;
    boardArray temp_board;
    queenArray temp_queenPos;
    memcpy(temp_board,board,sizeof(int)*BOARD_GRID_SIZE);//复制当前棋盘
    memcpy(temp_queenPos,queenPos,sizeof(int)*8);//复制当前红方皇后位置


    for (step = 0; step < MCTS_SIMULATION_STEPS; step++)
    {
        //下一步
        vecMovePos = getSideQueenOneMoveAction(temp_board, temp_queenPos, tempSide);

        if (vecMovePos.empty())
        {
            return tempSide == moveSide ? -1.0 : 1.0;
        }
        randomIndex = rand() % vecMovePos.size();

        //temp_board[vecMovePos[randomIndex].To / BOARD_SIZE][vecMovePos[randomIndex].To % BOARD_SIZE] = temp_board[vecMovePos[randomIndex].From / BOARD_SIZE][vecMovePos[randomIndex].From % BOARD_SIZE];
        //temp_board[vecMovePos[randomIndex].From / BOARD_SIZE][vecMovePos[randomIndex].From % BOARD_SIZE] = EMPTY;
        (*temp_board)[vecMovePos[randomIndex].To] = (*temp_board)[vecMovePos[randomIndex].From];
        (*temp_board)[vecMovePos[randomIndex].From] = EMPTY;

        updateQueenPos(temp_queenPos, tempSide, vecMovePos[randomIndex].From, vecMovePos[randomIndex].To);//更新皇后位置

        //放置障碍
        vecTemp = getExpandTerritory(temp_board, vecMovePos[randomIndex].To);

        if (!vecTemp.empty()) {
            randomIndex = rand() % vecTemp.size();
            temp_board[vecTemp[randomIndex] / BOARD_SIZE][vecTemp[randomIndex] % BOARD_SIZE] = STONE;
        }
        tempSide = -tempSide;
    }


    double leafValue = valueAll(temp_board, temp_queenPos, tempSide);
    return tempSide == moveSide ? leafValue : -leafValue;

}


/*
int uctSimulate(const boardArray& board, const queenArray& queenPos, int moveSide)
{
    const int SIM_COUNT = 7;  // 并行模拟次数 = 线程数
    int redWins = 0;
    int blueWins = 0;

    // === OpenMP 并行模拟 ===
    #pragma omp parallel for num_threads(SIM_COUNT) reduction(+:redWins, blueWins)
    for (int sim = 0; sim < SIM_COUNT; ++sim)
    {
        // 独立复制棋盘和皇后位置
        boardArray temp_board;
        queenArray temp_queenPos;
        memcpy(temp_board, board, sizeof(int) * BOARD_GRID_SIZE);
        memcpy(temp_queenPos, queenPos, sizeof(int) * 8);

        int tempSide = moveSide;
        int randomIndex;
        std::vector<int> vecTemp;
        std::vector<MoveAction> vecMovePos;

        // 每线程独立随机种子（防止相同序列）
        srand((unsigned)time(NULL) + sim * 37 + omp_get_thread_num() * 13);

        for (int step = 0; step < 6; step++)
        {
            vecMovePos = getSideQueenOneMoveAction(temp_board, temp_queenPos, tempSide);
            if (vecMovePos.empty())
            {
                if (-tempSide == RED_SIDE)
                    redWins++;
                else
                    blueWins++;
                goto next_sim;
            }

            randomIndex = rand() % vecMovePos.size();

            (*temp_board)[vecMovePos[randomIndex].To] = (*temp_board)[vecMovePos[randomIndex].From];
            (*temp_board)[vecMovePos[randomIndex].From] = EMPTY;

            updateQueenPos(temp_queenPos, tempSide,
                           vecMovePos[randomIndex].From,
                           vecMovePos[randomIndex].To);

            vecTemp = getExpandTerritory(temp_board, vecMovePos[randomIndex].To);
            if (!vecTemp.empty())
            {
                randomIndex = rand() % vecTemp.size();
                temp_board[vecTemp[randomIndex] / BOARD_SIZE]
                          [vecTemp[randomIndex] % BOARD_SIZE] = STONE;
            }

            tempSide = -tempSide;
        }

        // 模拟结束后计算局面价值
        if (valueAll(temp_board, temp_queenPos, RED_SIDE) >= 0)
            redWins++;
        else
            blueWins++;

    next_sim:
        continue;
    }

    // === 汇总并返回结果 ===
    if (redWins >= blueWins)
        return RED_SIDE;
    else
        return BLUE_SIDE;
}*/

//UCT算法的反向传播
void uctBackPropagation(UCTNode* node, double value)
{
    UCTNode* currentNode = node;
    while (currentNode != NULL)
    {
        currentNode->simulate.attempt++;
        currentNode->simulate.valueSum += value;
        value = -value;
        currentNode = currentNode->parent;
    }

}

void InitializeRandomSeed() {
    LARGE_INTEGER nFrequency;
    if (::QueryPerformanceFrequency(&nFrequency)) {
        LARGE_INTEGER nStartCounter;
        ::QueryPerformanceCounter(&nStartCounter);
        ::srand(nStartCounter.QuadPart); // 使用整个 64 位值作为种子
    }
    else {
        SYSTEMTIME st;
        ::GetLocalTime(&st);
        unsigned int seed = st.wYear * 10000 + st.wMonth * 100 + st.wDay;
        seed = seed * 60000 + st.wHour * 1000 + st.wMinute * 60 + st.wSecond;
        seed = seed * 1000 + st.wMilliseconds; // 使用完整的系统时间作为种子
        ::srand(seed);
    }
}

//uct算法
UctRes  uctAll(const boardArray& board,const queenArray& queenPos, int moveSide, double calTime,bool isDisplayInfo)
{


    //displayBoard(board);

    double uctTime = calTime;

    int maxAttempt = 0;
    double useTime;
    UctRes bestMoveInfo;

    /*if(isAllQuennSureTerritory(board) == true)
    {
        cout << "<isAllQuennSureTerritory>\n";
        uctTime = 5;
    }*/


    UCTNode* uctTree = NULL;

    uctTree = uctInitNode(board, queenPos, uctTree, moveSide);

    clock_t startTime = clock();

    while (1)
    {
        UCTNode* selectNode = uctSelect(uctTree);
        UCTNode* maxNode = uctExpand(selectNode);

        clock_t endTime = clock();

        useTime = (double)(endTime - startTime) / CLOCKS_PER_SEC;

        if (useTime > uctTime || uctTree->simulate.attempt > UCT_MAX_ATTEMPT_NUMBER)
        {
            if (uctTree->vecNodes.empty() == true)
            {
                system("pause");
            }

            UCTNode* bestNode = uctTree->vecNodes[0];

            maxAttempt = bestNode->simulate.attempt;

            int bestNumber = 0;

            for (int i = 0; i < uctTree->vecNodes.size(); i++)
            {
                int tempAttempt = uctTree->vecNodes[i]->simulate.attempt;

                if (tempAttempt > maxAttempt)
                {
                    bestNode = uctTree->vecNodes[i];
                    maxAttempt = tempAttempt;
                    bestNumber = i;
                }
            }



            bestMoveInfo.From = bestNode->action.From;
            bestMoveInfo.To = bestNode->action.To;
            bestMoveInfo.Stone = bestNode->action.Stone;
            bestMoveInfo.attempt = bestNode->parent->simulate.attempt;
            bestMoveInfo.value = bestNode->message.value;
            bestMoveInfo.pro = 50.0 *
                (bestNode->simulate.valueSum / bestNode->simulate.attempt + 1.0);
            //cout << uctTree->simulate.attempt;
            //uctDisplayUCTNode(uctTree);
            //double thisTime = (double)(endTime - startTime) / CLOCKS_PER_SEC;
            //allTime += thisTime;
            //printf("<This Time :%0.1fs. All time:%0.2fmin. Count:%d>",thisTime,allTime/60.0,moveCount);


            double uctPro = 50.0 *
                (bestNode->simulate.valueSum / bestNode->simulate.attempt + 1.0);


            if (isDisplayInfo)
            {
                double  w = 0;
                valueT1(board, queenPos, moveSide, &w);



                if (moveSide == RED_SIDE)
                {
                    printf("red");
                }
                else
                {
                    printf("blue");
                }


                printf("(From:%d,To:%d,Stone:%d)|%f|", bestNode->action.From, bestNode->action.To, bestNode->action.Stone, w);
                printf("(attemp:%d/%d,number: %d/%d,value:%.2f,pro:%0.0f)\n", bestNode->simulate.attempt, uctTree->simulate.attempt, bestNumber, uctTree->vecNodes.size(),
                    bestNode->message.value, 50.0 *
                    (bestNode->simulate.valueSum / bestNode->simulate.attempt + 1.0));
                //printf("(|%.0f|[%d/%d][value:%.2f][%0.0f]\n",checkW(board),bestNode->simulate.attempt,uctTree->simulate.attempt,
                       //bestNode->message.value,( (double)(bestNode->simulate.win + bestNode->simulate.attempt)/bestNode->simulate.attempt/2 )*100);

                //winPos = ( (double)(bestNode->simulate.win + bestNode->simulate.attempt)/bestNode->simulate.attempt/2 )*100;
            }

            deleteRoot(uctTree);
            break;
        }
    }


    return bestMoveInfo;
}

// 辅助函数：将 py::array_t 转换为 C++ 静态数组 (10x10 board)
void convert_pyarray_to_carray(py::array_t<int> py_board, boardArray& c_board) {
    py::buffer_info buf = py_board.request();
    if (buf.ndim != 2 || buf.shape[0] != BOARD_SIZE || buf.shape[1] != BOARD_SIZE) {
        throw std::runtime_error("Board shape must be (10, 10)");
    }
    int *ptr = (int *)buf.ptr;
    // 使用 memcpy 比逐个赋值更快，但需要谨慎处理内存布局
    std::memcpy(c_board, ptr, sizeof(int) * BOARD_GRID_SIZE);
}

// 辅助函数：将 py::list 转换为 C++ 静态数组 (2x4 queenPos)
void convert_pylist_to_carray(py::list py_queens, queenArray& c_queens) {
    if (py_queens.size() != 2) {
        throw std::runtime_error("Queen positions must be a list of 2 lists/arrays.");
    }
    for (int side = 0; side < 2; ++side) {
        py::list side_queens = py_queens[side];
        if (side_queens.size() != 4) {
            throw std::runtime_error("Each side must have 4 queen positions.");
        }
        for (int i = 0; i < 4; ++i) {
            c_queens[side][i] = side_queens[i].cast<int>();
        }
    }
}



class AmazonasAI {
public:
    // 构造函数：无状态类，无需参数
    AmazonasAI() {
        InitializeRandomSeed();
    }
    ~AmazonasAI() {}

    // 核心函数：包装并调用原始的 uctAll
    UctRes uctSearch(py::array_t<int> initialBoard, py::list initialQueenPos, int moveSide, double calTime, bool isDisplayInfo) {
        // 1. 将 Python 数据结构转换为 C++ 静态数组
        boardArray board;
        queenArray queenPos;
        convert_pyarray_to_carray(initialBoard, board);
        convert_pylist_to_carray(initialQueenPos, queenPos);

        // 2. 搜索期间不访问 Python 对象，释放 GIL，避免冻结 Qt 主线程。
        UctRes result;
        {
            py::gil_scoped_release release;
            result = uctAll(board, queenPos, moveSide, calTime, isDisplayInfo);
        }
        return result;
    }

    py::dict evaluateFeatures(py::array_t<int> initialBoard, py::list initialQueenPos, int moveSide) {
        boardArray board;
        queenArray queenPos;
        convert_pyarray_to_carray(initialBoard, board);
        convert_pylist_to_carray(initialQueenPos, queenPos);

        std::array<double, EVALUATION_FEATURE_COUNT> features =
            calculateEvaluationFeatures(
            board, queenPos, moveSide);
        py::dict result;
        static const char* featureNames[EVALUATION_FEATURE_COUNT] = {
            "t1", "t2", "c1", "c2", "mobility", "w", "empty_count",
            "secure_territory", "contested_count", "queen_mobility",
            "weakest_queen_mobility", "queen_mobility_balance", "liberties",
            "weakest_liberties", "trapped_queens", "reach_overlap",
            "center_control", "queen_spread", "combat_mobility",
            "weakest_combat_mobility", "active_queens",
            "exclusive_queen_redundancy", "active_area_count",
            "blocker_queens", "blocker_swing", "gateway_control",
            "queen_load_min", "queen_load_balance", "access_redundancy",
            "territory_dead_end_risk", "territory_cut_risk",
            "second_weakest_combat_mobility", "strongest_combat_mobility",
            "combat_mobility_balance", "combat_active_queens"
        };
        for (int index = 0; index < EVALUATION_FEATURE_COUNT; ++index) {
            result[featureNames[index]] = features[index];
        }
        std::array<double, gen217_value_model::INPUT_SIZE> modelFeatures = {};
        for (int index = 0; index < gen217_value_model::INPUT_SIZE; ++index) {
            modelFeatures[index] = features[index];
        }
        result["rich_value"] = gen217_value_model::evaluate(modelFeatures);
        result["value"] = valueAll(board, queenPos, moveSide);
        return result;
    }
};




// ===========================================
// pybind11 封装部分
// ===========================================
#ifndef AMAZON_AI_MODULE_NAME
#define AMAZON_AI_MODULE_NAME amazon_ai
#endif

PYBIND11_MODULE(AMAZON_AI_MODULE_NAME, m) {
    m.doc() = "pybind11 wrapper for the Amazonas UCT C++ AI"; // 模块文档字符串

    // 1. 绑定 UctRes 结构体
    py::class_<UctRes>(m, "UctRes", py::module_local())
        .def(py::init<>())
        .def_readwrite("From", &UctRes::From)
        .def_readwrite("To", &UctRes::To)
        .def_readwrite("Stone", &UctRes::Stone)
        // 绑定新增的成员
        .def_readwrite("attempt", &UctRes::attempt)
        .def_readwrite("value", &UctRes::value)
        .def_readwrite("pro", &UctRes::pro)
        .def("__repr__", [](const UctRes& a) {
            // 使用 std::ostringstream 构造更清晰的 repr 字符串，便于调试
            std::ostringstream os;
            os << "<UctRes From:" << a.From
               << " To:" << a.To
               << " Stone:" << a.Stone
               << " attempt:" << a.attempt
               << " value:" << a.value
               << " pro:" << a.pro << ">";
            return os.str();
        });

    // 2. 绑定 AmazonasAI 类
    py::class_<AmazonasAI>(m, "AmazonasAI", py::module_local())
        // 绑定无参数构造函数
        .def(py::init<>())
        // 绑定 uctSearch 函数
        .def("uct_search", &AmazonasAI::uctSearch,
             py::arg("initialBoard"),
             py::arg("initialQueenPos"),
             py::arg("moveSide"),
             py::arg("calTime"),
             py::arg("isDisplayInfo") = false, // 将可选参数 isDisplayInfo 绑定
             "Runs UCT/MCTS search on the given board state and returns the best move.")
        .def("evaluate_features", &AmazonasAI::evaluateFeatures,
             py::arg("initialBoard"),
             py::arg("initialQueenPos"),
             py::arg("moveSide"),
             "Returns the fitted evaluator inputs and continuous value.")
        // 绑定 __repr__
        .def("__repr__", [](const AmazonasAI &a) {
            return "<AmazonasAI object>";
        });
}
