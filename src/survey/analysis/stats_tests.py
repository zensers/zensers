"""
Statistical Tests Module

Pure-Python implementations of common statistical tests for survey analysis.
Zero external dependencies — uses only math module.

Includes:
  - Independent t-test (Welch's) with Cohen's d
  - One-way ANOVA with F-test
  - Chi-square test of independence
  - Pearson correlation
  - Mann-Whitney U test (non-parametric)
  - Kruskal-Wallis H test (non-parametric, 3+ groups)
"""

import math
from typing import Any, Dict, List


# ------------------------------------------------------------------ #
# Validation helper
# ------------------------------------------------------------------ #

def _validate_numeric(values, name="input"):
    """Check list for NaN/Inf. Raises ValueError if found."""
    for i, v in enumerate(values):
        if isinstance(v, (int, float)):
            if math.isnan(v) or math.isinf(v):
                raise ValueError(f"{name}[{i}] is NaN or Inf: {v}")


def _validate_2d(table, name="table"):
    """Check 2D list is rectangular and contains valid numbers."""
    if not table or not table[0]:
        raise ValueError(f"{name} must not be empty")
    n_cols = len(table[0])
    for i, row in enumerate(table):
        if len(row) != n_cols:
            raise ValueError(f"{name}[{i}] has {len(row)} columns, expected {n_cols}")
        _validate_numeric(row, f"{name}[{i}]")


def _unwrap_group_args(groups):
    """Allow both separate args and single list-of-lists."""
    if len(groups) == 1 and isinstance(groups[0], list) and groups[0] and isinstance(groups[0][0], list):
        return groups[0]
    return list(groups)


# ------------------------------------------------------------------ #
# P-value approximations
# ------------------------------------------------------------------ #

def _log_gamma(x: float) -> float:
    """Lanczos approximation for log-gamma function (g=7)."""
    if x <= 0:
        return float("inf")
    g = 7
    c = [0.99999999999980993, 676.5203681218851, -1259.1392167224028,
         771.32342877765313, -176.61502916214059, 12.507343278686905,
         -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7]
    xm1 = x - 1
    zh = xm1 + 0.5
    z = xm1 + g + 0.5
    s = c[0]
    for i in range(1, len(c)):
        s += c[i] / (xm1 + i)
    if s <= 0:
        return float("inf")
    return zh * math.log(z) - z + 0.5 * math.log(2 * math.pi) + math.log(s)


def _beta_regularized(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a,b) using Lentz continued fraction."""
    if x < 0 or x > 1:
        return 1.0
    if x == 0 or x == 1:
        return x
    # Use symmetry to ensure convergence
    if x > (a + 1) / (a + b + 2):
        return 1 - _beta_regularized(b, a, 1 - x)
    # Compute prefix: x^a * (1-x)^b / (a * B(a,b))
    ln_gab = _log_gamma(a + b) - _log_gamma(a) - _log_gamma(b)
    front = math.exp(ln_gab + a * math.log(x) + b * math.log(1 - x)) / a
    if front == 0 or not math.isfinite(front):
        return 0.0
    # Lentz continued fraction
    f = 1.0
    c_frac = 1.0
    d_frac = 1.0 - (a + b) * x / (a + 1)
    if abs(d_frac) < 1e-30:
        d_frac = 1e-30
    d_frac = 1.0 / d_frac
    c_frac = 1.0
    f = d_frac
    for m in range(1, 201):
        # Even step
        numer = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d_frac = 1.0 + numer * d_frac
        if abs(d_frac) < 1e-30:
            d_frac = 1e-30
        c_frac = 1.0 + numer / c_frac
        if abs(c_frac) < 1e-30:
            c_frac = 1e-30
        d_frac = 1.0 / d_frac
        delta = c_frac * d_frac
        f *= delta
        # Odd step
        numer = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d_frac = 1.0 + numer * d_frac
        if abs(d_frac) < 1e-30:
            d_frac = 1e-30
        c_frac = 1.0 + numer / c_frac
        if abs(c_frac) < 1e-30:
            c_frac = 1e-30
        d_frac = 1.0 / d_frac
        delta = c_frac * d_frac
        f *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return front * f


def _t_twotail(t: float, df: float) -> float:
    """Two-tailed p-value from t-distribution."""
    x = df / (df + t * t)
    return _beta_regularized(df / 2, 0.5, x)


def _f_upper(f: float, df1: float, df2: float) -> float:
    """Upper-tail p-value from F-distribution."""
    x = df2 / (df2 + df1 * f)
    return _beta_regularized(df2 / 2, df1 / 2, x)


def _gamma_upper(a: float, x: float) -> float:
    """Upper regularized gamma function Q(a,x) via continued fraction."""
    if x <= 0 or a <= 0:
        return 1.0 if x <= 0 else 0.0
    # Use series for small x
    if x < a + 1:
        s = 0.0
        term = 1.0 / a
        for n in range(1, 201):
            s += term
            term *= x / (a + n)
            if abs(term) < 1e-14:
                break
        ln_g = _log_gamma(a)
        if not math.isfinite(ln_g):
            return 0.0
        return 1 - math.exp(a * math.log(x) - x - ln_g) * s
    # Lentz continued fraction for large x
    ln_g = _log_gamma(a)
    if not math.isfinite(ln_g):
        return 0.0
    front = math.exp(a * math.log(x) - x - ln_g)
    f = x + 1 - a
    if abs(f) < 1e-30:
        f = 1e-30
    c_frac = 1.0
    d_frac = 1.0 / f
    h = d_frac
    for m in range(1, 201):
        an = -m * (m - a)
        bn = x + 2 * m + 1 - a
        d_frac = bn + an * d_frac
        if abs(d_frac) < 1e-30:
            d_frac = 1e-30
        c_frac = bn + an / c_frac
        if abs(c_frac) < 1e-30:
            c_frac = 1e-30
        d_frac = 1.0 / d_frac
        delta = c_frac * d_frac
        h *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    return front * h


def _chi2_upper(x: float, df: float) -> float:
    """Upper-tail p-value from chi-square distribution."""
    return _gamma_upper(df / 2, x / 2)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using Winitzki approximation (max error ~0.00014)."""
    a = 0.147
    s = 1 if x >= 0 else -1
    x2 = x * x
    return 0.5 * (1 + s * math.sqrt(1 - math.exp(-x2 * (2 / math.pi + a * x2 / (1 + a * x2)))))


# ------------------------------------------------------------------ #
# Group stats helper
# ------------------------------------------------------------------ #

def _group_stats(values: List[float]) -> Dict[str, Any]:
    """Mean, variance, std, n for a list of values."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": 0.0, "var": 0.0, "std": 0.0}
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return {"n": n, "mean": mean, "var": var, "std": math.sqrt(var)}


# ------------------------------------------------------------------ #
# Independent t-test (Welch's)
# ------------------------------------------------------------------ #

def ttest_ind(group_a: List[float], group_b: List[float]) -> Dict[str, Any]:
    """Independent samples t-test (Welch's, unequal variance).

    Args:
        group_a: Numeric responses for group A
        group_b: Numeric responses for group B

    Returns:
        Dict with t_stat, df, p_value, cohens_d, mean_a, mean_b, n_a, n_b, significant
    """
    _validate_numeric(group_a, "group_a")
    _validate_numeric(group_b, "group_b")

    sa = _group_stats(group_a)
    sb = _group_stats(group_b)
    n_a, n_b = sa["n"], sb["n"]

    if n_a < 2 or n_b < 2:
        return {"t_stat": 0.0, "df": 0.0, "p_value": 1.0, "cohens_d": 0.0,
                "mean_a": sa["mean"], "mean_b": sb["mean"], "n_a": n_a, "n_b": n_b,
                "significant": False}

    se = math.sqrt(sa["var"] / n_a + sb["var"] / n_b)
    if se == 0:
        return {"t_stat": 0.0, "df": 0.0, "p_value": 1.0, "cohens_d": 0.0,
                "mean_a": sa["mean"], "mean_b": sb["mean"], "n_a": n_a, "n_b": n_b,
                "significant": False}

    t = (sa["mean"] - sb["mean"]) / se

    # Welch-Satterthwaite df
    num = (sa["var"] / n_a + sb["var"] / n_b) ** 2
    denom = (sa["var"] / n_a) ** 2 / (n_a - 1) + (sb["var"] / n_b) ** 2 / (n_b - 1)
    df = num / denom if denom > 0 else 1.0

    p = _t_twotail(t, df)

    # Cohen's d (pooled)
    pool_var = ((n_a - 1) * sa["var"] + (n_b - 1) * sb["var"]) / (n_a + n_b - 2)
    d = (sa["mean"] - sb["mean"]) / math.sqrt(pool_var) if pool_var > 0 else 0.0

    return {
        "t_stat": round(t, 4),
        "df": round(df, 2),
        "p_value": round(p, 4),
        "cohens_d": round(abs(d), 4),
        "mean_a": round(sa["mean"], 4),
        "mean_b": round(sb["mean"], 4),
        "n_a": n_a,
        "n_b": n_b,
        "significant": p < 0.05,
    }


# ------------------------------------------------------------------ #
# One-way ANOVA
# ------------------------------------------------------------------ #

def oneway_anova(*groups: List[float]) -> Dict[str, Any]:
    """One-way ANOVA (F-test) for 2+ groups.

    Args:
        *groups: Two or more lists of numeric responses.
                 Can also pass a single list-of-lists: oneway_anova([g1, g2, g3])

    Returns:
        Dict with f_stat, df_between, df_within, p_value, group_stats, significant
    """
    groups = _unwrap_group_args(groups)
    for i, g in enumerate(groups):
        _validate_numeric(g, f"group[{i}]")

    group_stats = [_group_stats(g) for g in groups if len(g) > 0]
    k = len(group_stats)
    if k < 2:
        return {"f_stat": 0.0, "df_between": 0, "df_within": 0, "p_value": 1.0,
                "grand_mean": 0.0, "n_total": 0, "significant": False,
                "group_stats": [{"name": f"Group {i+1}", "n": 0, "mean": 0.0, "std": 0.0}
                                for i in range(k)]}

    n_total = sum(gs["n"] for gs in group_stats)
    grand_mean = sum(gs["mean"] * gs["n"] for gs in group_stats) / n_total

    ss_between = sum(gs["n"] * (gs["mean"] - grand_mean) ** 2 for gs in group_stats)
    ss_within = sum((gs["n"] - 1) * gs["var"] for gs in group_stats)

    df_between = k - 1
    df_within = n_total - k

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within if df_within > 0 else 0.0

    f_stat = ms_between / ms_within if ms_within > 0 else 0.0
    p = _f_upper(f_stat, df_between, df_within) if f_stat > 0 else 1.0

    return {
        "f_stat": round(f_stat, 4),
        "df_between": df_between,
        "df_within": df_within,
        "p_value": round(p, 4),
        "grand_mean": round(grand_mean, 4),
        "n_total": n_total,
        "significant": p < 0.05,
        "group_stats": [
            {"name": f"Group {i+1}", "n": gs["n"], "mean": round(gs["mean"], 4),
             "std": round(gs["std"], 4)}
            for i, gs in enumerate(group_stats)
        ],
    }


# ------------------------------------------------------------------ #
# Chi-square test of independence
# ------------------------------------------------------------------ #

def chi_square(observed: List[List[float]]) -> Dict[str, Any]:
    """Chi-square test of independence for a contingency table.

    Args:
        observed: 2D list of observed frequencies (rows x columns)

    Returns:
        Dict with chi2_stat, df, p_value, expected, significant
    """
    _validate_2d(observed, "observed")
    n_rows = len(observed)
    n_cols = len(observed[0])

    row_totals = [sum(row) for row in observed]
    col_totals = [sum(observed[i][j] for i in range(n_rows)) for j in range(n_cols)]
    grand_total = sum(row_totals)

    if grand_total == 0:
        return {"chi2_stat": 0.0, "df": 0, "p_value": 1.0, "expected": observed,
                "significant": False}

    expected = [[row_totals[i] * col_totals[j] / grand_total for j in range(n_cols)]
                for i in range(n_rows)]

    chi2 = 0.0
    for i in range(n_rows):
        for j in range(n_cols):
            if expected[i][j] > 0:
                chi2 += (observed[i][j] - expected[i][j]) ** 2 / expected[i][j]

    df = (n_rows - 1) * (n_cols - 1)
    p = _chi2_upper(chi2, df) if df > 0 else 1.0

    return {
        "chi2_stat": round(chi2, 4),
        "df": df,
        "p_value": round(p, 4),
        "expected": [[round(v, 2) for v in row] for row in expected],
        "significant": p < 0.05,
    }


# ------------------------------------------------------------------ #
# Pearson correlation
# ------------------------------------------------------------------ #

def pearson_r(x: List[float], y: List[float]) -> Dict[str, Any]:
    """Pearson correlation coefficient with significance test.

    Args:
        x: First variable
        y: Second variable

    Returns:
        Dict with r, r_squared, p_value, n, significant
    """
    _validate_numeric(x, "x")
    _validate_numeric(y, "y")
    if len(x) != len(y):
        raise ValueError(f"x and y must have same length ({len(x)} vs {len(y)})")

    n = len(x)
    if n < 3:
        return {"r": 0.0, "r_squared": 0.0, "p_value": 1.0, "n": n, "significant": False}

    mx = sum(x) / n
    my = sum(y) / n

    sxx = sum((xi - mx) ** 2 for xi in x)
    syy = sum((yi - my) ** 2 for yi in y)
    sxy = sum((x[i] - mx) * (y[i] - my) for i in range(n))

    denom = math.sqrt(sxx * syy)
    r = sxy / denom if denom > 0 else 0.0
    r = max(-1.0, min(1.0, r))

    # t-test for significance
    eps = 1e-10
    t_val = r * math.sqrt(max(eps, n - 2) / max(eps, 1 - r * r))
    p_val = _t_twotail(abs(t_val), n - 2)

    return {
        "r": round(r, 4),
        "r_squared": round(r * r, 4),
        "p_value": round(p_val, 4),
        "n": n,
        "significant": p_val < 0.05,
    }


# ------------------------------------------------------------------ #
# Mann-Whitney U test (non-parametric)
# ------------------------------------------------------------------ #

def mannwhitney_u(group_a: List[float], group_b: List[float]) -> Dict[str, Any]:
    """Mann-Whitney U test for two independent groups.

    Non-parametric alternative to independent t-test.
    Does NOT assume normal distribution.

    Returns:
        Dict with u_stat, p_value, z_score, n_a, n_b, median_a, median_b, significant
    """
    _validate_numeric(group_a, "group_a")
    _validate_numeric(group_b, "group_b")

    n_a, n_b = len(group_a), len(group_b)
    if n_a < 2 or n_b < 2:
        return {"u_stat": 0.0, "p_value": 1.0, "z_score": 0.0,
                "n_a": n_a, "n_b": n_b,
                "median_a": 0.0, "median_b": 0.0, "significant": False}

    combined = [(v, 0) for v in group_a] + [(v, 1) for v in group_b]
    combined.sort(key=lambda x: x[0])

    # Ranks with tie handling
    ranks = []
    i = 0
    while i < len(combined):
        j = i
        while j < len(combined) and combined[j][0] == combined[i][0]:
            j += 1
        rank = (i + j + 1) / 2  # mean rank for ties
        for kk in range(i, j):
            ranks.append((rank, combined[kk][1]))
        i = j

    r_a = sum(r for r, g in ranks if g == 0)
    u1 = r_a - n_a * (n_a + 1) / 2
    u2 = n_a * n_b - u1
    u_stat = min(u1, u2)

    # Tie correction
    tie_counts = {}
    for v, _ in combined:
        tie_counts[v] = tie_counts.get(v, 0) + 1
    tie_correction = sum(t ** 3 - t for t in tie_counts.values() if t > 1)
    n = n_a + n_b
    tie_factor = 1 - tie_correction / (n ** 3 - n) if n ** 3 - n > 0 else 1.0
    tie_factor = max(tie_factor, 0.01)  # prevent zero

    # Normal approximation with continuity correction
    mu = n_a * n_b / 2
    sigma = math.sqrt(n_a * n_b * (n + 1) * tie_factor / 12)
    if sigma == 0:
        z = 0.0
    else:
        z = (abs(u_stat - mu) - 0.5) / sigma  # continuity correction
        z = max(z, 0.0)
    p = 2 * (1 - _norm_cdf(z))

    # Medians
    sa = sorted(group_a)
    sb = sorted(group_b)
    median_a = (sa[n_a // 2 - 1] + sa[n_a // 2]) / 2 if n_a % 2 == 0 else sa[n_a // 2]
    median_b = (sb[n_b // 2 - 1] + sb[n_b // 2]) / 2 if n_b % 2 == 0 else sb[n_b // 2]

    return {
        "u_stat": round(u_stat, 2),
        "p_value": round(p, 4),
        "z_score": round(z, 4),
        "n_a": n_a,
        "n_b": n_b,
        "median_a": round(median_a, 4),
        "median_b": round(median_b, 4),
        "significant": p < 0.05,
    }


# ------------------------------------------------------------------ #
# Kruskal-Wallis H test (non-parametric, 2+ groups)
# ------------------------------------------------------------------ #

def kruskal_wallis(*groups: List[float]) -> Dict[str, Any]:
    """Kruskal-Wallis H test for 2+ independent groups.

    Non-parametric alternative to one-way ANOVA.
    Does NOT assume normal distribution.

    Args:
        *groups: Two or more lists of numeric responses.
                 Can also pass a single list-of-lists.

    Returns:
        Dict with h_stat, df, p_value, n_total, k, significant
    """
    groups = _unwrap_group_args(groups)
    for i, g in enumerate(groups):
        _validate_numeric(g, f"group[{i}]")

    n_groups = len([g for g in groups if len(g) > 0])
    n_total = sum(len(g) for g in groups)

    if n_groups < 2 or n_total < 2:
        return {"h_stat": 0.0, "df": max(n_groups - 1, 0), "p_value": 1.0,
                "n_total": n_total, "k": n_groups, "significant": False}

    combined = []
    for i, g in enumerate(groups):
        for v in g:
            combined.append((v, i))
    combined.sort(key=lambda x: x[0])

    # Ranks with tie handling
    ranks = []
    idx = 0
    while idx < len(combined):
        j = idx
        while j < len(combined) and combined[j][0] == combined[idx][0]:
            j += 1
        rank_val = (idx + j + 1) / 2
        for kk in range(idx, j):
            ranks.append((rank_val, combined[kk][1]))
        idx = j

    group_rank_sums = [0.0] * n_groups
    group_counts = [0] * n_groups
    for rv, gi in ranks:
        group_rank_sums[gi] += rv
        group_counts[gi] += 1

    # H statistic
    h = 12 / (n_total * (n_total + 1)) * sum(
        rs ** 2 / cnt for rs, cnt in zip(group_rank_sums, group_counts) if cnt > 0
    ) - 3 * (n_total + 1)

    # Tie correction
    tie_counts = {}
    for v, _ in combined:
        tie_counts[v] = tie_counts.get(v, 0) + 1
    tie_correction = sum(t ** 3 - t for t in tie_counts.values() if t > 1)
    h /= max(1 - tie_correction / (n_total ** 3 - n_total), 0.01) if n_total ** 3 > n_total else 1.0

    df = n_groups - 1
    p = _chi2_upper(h, df) if df > 0 else 1.0

    return {
        "h_stat": round(h, 4),
        "df": df,
        "p_value": round(p, 4),
        "n_total": n_total,
        "k": n_groups,
        "significant": p < 0.05,
    }
