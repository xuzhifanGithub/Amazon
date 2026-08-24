#pragma once

#include <algorithm>
#include <cmath>

namespace gen217_value_blend {
static const int PHASE_DEGREE = 3;
static const double PHASE_DIVISOR = 92.0;
static const double COEFFICIENTS[3][PHASE_DEGREE + 1] = {
    {0.10298515627915505, -0.5527907016125421, 0.7252903392919319, -0.21099121479578506},
    {0.23919454846191485, 1.587987231239559, 0.2407440932652297, -2.351501549248754},
    {1.0014609880518839, -6.957159668674252, 19.816817661194598, -16.344758892508136}
};

inline double polynomial(int group, double phase) {
    double result = COEFFICIENTS[group][PHASE_DEGREE];
    for (int degree = PHASE_DEGREE - 1; degree >= 0; --degree)
        result = result * phase + COEFFICIENTS[group][degree];
    return result;
}

inline double logit(double value) {
    value = std::max(-0.999999, std::min(0.999999, value));
    return 2.0 * std::atanh(value);
}

inline double evaluate(double rich, double legacy, double rawPhase) {
    double phase = std::max(0.0, std::min(1.0, rawPhase / PHASE_DIVISOR));
    double combined = polynomial(0, phase)
        + polynomial(1, phase) * logit(rich)
        + polynomial(2, phase) * logit(legacy);
    return std::tanh(0.5 * combined);
}
}  // namespace gen217_value_blend
