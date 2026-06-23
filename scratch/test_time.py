import pandas as pd

# Test case 1: Standard HH:MM:SS
s1 = pd.Series(["08:30:00", "17:45:15", None])
t1 = pd.to_datetime(s1, errors="coerce", format="mixed")
print("Standard HH:MM:SS:")
print("parsed_dt:")
print(t1)
print("dt.time:")
print(t1.dt.time)

# Test case 2: Time string without seconds
s2 = pd.Series(["08:30", "17:45", None])
t2 = pd.to_datetime(s2, errors="coerce", format="mixed")
print("\nTime string without seconds:")
print("parsed_dt:")
print(t2)
print("dt.time:")
print(t2.dt.time)

# Test case 3: Check isna on the result
print("\nisna on t1.dt.time:")
print(t1.dt.time.isna())
print("isna on list(t1.dt.time):")
print(pd.Series(list(t1.dt.time)).isna())
