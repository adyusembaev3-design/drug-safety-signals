"""Shared definitions: risk groups, JAK drugs, comparator set, ROR calculation."""
import math

GROUPS = {
    "Thrombosis / embolism": "pt LIKE '%THROMBOSIS%' OR pt LIKE '%EMBOLISM%'",
    "Herpes zoster": "pt LIKE 'HERPES ZOSTER%'",
    "Serious infection": (
        "pt LIKE '%PNEUMONIA%' OR pt LIKE '%SEPSIS%' OR pt LIKE '%TUBERCULOSIS%'"
    ),
    "Malignancy": (
        "pt LIKE '%LYMPHOMA%' OR pt LIKE '%NEOPLASM MALIGNANT%' "
        "OR pt LIKE '%CARCINOMA%' OR pt LIKE '%MALIGNANT MELANOMA%'"
    ),
    "Heart attack / stroke": (
        "pt LIKE '%MYOCARDIAL INFARCTION%' OR pt = 'CEREBROVASCULAR ACCIDENT'"
    ),
    "Raised cholesterol": (
        "pt LIKE '%CHOLESTEROL INCREASED%' OR pt LIKE '%HYPERCHOLESTEROLAEMIA%' "
        "OR pt = 'BLOOD CHOLESTEROL ABNORMAL'"
    ),
}

TARGETS = ["TOFACITINIB", "UPADACITINIB", "BARICITINIB"]

# Comparator arthritis drugs. Rituximab was removed after the first run because
# it is mainly used to treat lymphoma, which inflated the malignancy background.
REF = (
    "ADALIMUMAB|ETANERCEPT|INFLIXIMAB|GOLIMUMAB|CERTOLIZUMAB|"
    "ABATACEPT|TOCILIZUMAB|SARILUMAB"
)


def ror(a, b, c, d):
    """Reporting odds ratio with 0.5 continuity correction and 95% CI."""
    a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    est = (a * d) / (b * c)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    return est, math.exp(math.log(est) - 1.96 * se), math.exp(math.log(est) + 1.96 * se)
