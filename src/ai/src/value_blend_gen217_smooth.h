#pragma once

#include <algorithm>
#include <cmath>

namespace gen217_value_blend {
static const int PHASE_DEGREE = 3;
static const double PHASE_DIVISOR = 92.0;
static const double COEFFICIENTS[3][PHASE_DEGREE + 1] = {
    {0.08550103327084158, -0.6563697990387378, 1.554179827199009, -1.1689881752220896},
    {0.2980576243356843, 0.4002181470432653, 2.8057190526102826, -3.64831377176196},
    {0.8587758345474629, -3.0042399460220737, 5.281775543894966, -2.9256956302687467}
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
