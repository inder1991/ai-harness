# v1.3.0 S5 — trailing comment containing the literal text `shell=True`
# must NOT trigger the dangerous-pattern rule (pre-v1.3.0 false positive).
def example():
    x = "demo"  # shell=True example, but no actual subprocess
    return x
