import sys
from pyspark.context import SparkContext  # type: ignore
from awsglue.context import GlueContext  # type: ignore
# Note: pyspark and awsglue imports are resolved in the AWS Glue runtime.
# These Pylance warnings in VS Code are expected locally.
from pyspark.sql import functions as F
from pyspark.sql.window import Window

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

# ── READ ───────────────────────────────────────────────────
df = spark.read.csv(
    "s3://pharma-demo-3/raw/salesdaily.csv",
    header=True, inferSchema=True
)

# Fix data types
df = df.withColumn("Month", F.col("Month").cast("integer"))
df = df.withColumn("Year", F.col("Year").cast("integer"))

# ── T1: Therapy Area Grouping ──────────────────────────────
df = df.withColumn("anti_inflammatory_total",
        F.col("M01AB") + F.col("M01AE"))
df = df.withColumn("analgesics_total",
        F.col("N02BA") + F.col("N02BE"))
df = df.withColumn("cns_drugs_total",
        F.col("N05B") + F.col("N05C"))
df = df.withColumn("respiratory_total",
        F.col("R03") + F.col("R06"))
df = df.withColumn("total_daily_sales",
        F.col("anti_inflammatory_total") +
        F.col("analgesics_total") +
        F.col("cns_drugs_total") +
        F.col("respiratory_total"))

# ── T2: Dominant Therapy Per Day ───────────────────────────
df = df.withColumn("dominant_therapy",
    F.when(
        (F.col("anti_inflammatory_total") >= F.col("analgesics_total")) &
        (F.col("anti_inflammatory_total") >= F.col("cns_drugs_total")) &
        (F.col("anti_inflammatory_total") >= F.col("respiratory_total")),
        "Anti-Inflammatory"
    ).when(
        (F.col("analgesics_total") >= F.col("cns_drugs_total")) &
        (F.col("analgesics_total") >= F.col("respiratory_total")),
        "Analgesics"
    ).when(
        F.col("cns_drugs_total") >= F.col("respiratory_total"),
        "CNS Drugs"
    ).otherwise("Respiratory")
)

# ── T3: Weekend vs Weekday ─────────────────────────────────
df = df.withColumn("day_type",
        F.when(F.col("`Weekday Name`").isin(["Saturday","Sunday"]),
               "Weekend")
        .otherwise("Weekday"))

# ── T4: Performance Flag ───────────────────────────────────
mean_sales = df.agg(F.avg("total_daily_sales")).collect()[0][0]
df = df.withColumn("performance_flag",
        F.when(F.col("total_daily_sales") < mean_sales * 0.8,
               "Underperforming")
        .otherwise("On Track"))

# ── T5: Quarter ────────────────────────────────────────────
df = df.withColumn("Quarter",
        F.when(F.col("Month").isin([1,2,3]), "Q1")
        .when(F.col("Month").isin([4,5,6]), "Q2")
        .when(F.col("Month").isin([7,8,9]), "Q3")
        .otherwise("Q4"))

# ── ENHANCED DATA QUALITY CHECKS ──────────────────────────
print("=== RUNNING DATA QUALITY CHECKS ===")

total_records = df.count()
null_dates = df.filter(F.col("datum").isNull()).count()
negative_sales = df.filter(F.col("total_daily_sales") < 0).count()
zero_sales = df.filter(F.col("total_daily_sales") == 0).count()
duplicate_dates = total_records - df.dropDuplicates(["datum"]).count()
date_min = df.agg(F.min("datum")).collect()[0][0]
date_max = df.agg(F.max("datum")).collect()[0][0]
avg_sales = round(df.agg(F.avg("total_daily_sales")).collect()[0][0], 2)
underperforming_count = df.filter(
    F.col("performance_flag") == "Underperforming").count()

print(f"Total Records     : {total_records}")
print(f"Null Dates        : {null_dates}")
print(f"Negative Sales    : {negative_sales}")
print(f"Zero Sales Days   : {zero_sales}")
print(f"Duplicate Dates   : {duplicate_dates}")
print(f"Date Range        : {date_min} to {date_max}")
print(f"Avg Daily Sales   : {avg_sales}")
print(f"Underperforming   : {underperforming_count} days")

# ── WRITE QUALITY REPORT TO S3 ────────────────────────────
quality_data = [
    ("total_records",       str(total_records),    "INFO"),
    ("null_dates",          str(null_dates),        
     "PASS" if null_dates == 0 else "FAIL"),
    ("negative_sales",      str(negative_sales),    
     "PASS" if negative_sales == 0 else "FAIL"),
    ("zero_sales_days",     str(zero_sales),        
     "PASS" if zero_sales < 10 else "WARN"),
    ("duplicate_dates",     str(duplicate_dates),   
     "PASS" if duplicate_dates == 0 else "FAIL"),
    ("date_range_start",    str(date_min),          "INFO"),
    ("date_range_end",      str(date_max),          "INFO"),
    ("avg_daily_sales",     str(avg_sales),         "INFO"),
    ("underperforming_days",str(underperforming_count), "INFO"),
]

quality_df = spark.createDataFrame(
    quality_data,
    ["check_name", "result", "status"]
)

quality_df.write.mode("overwrite").parquet(
    "s3://pharma-demo-3/quality-reports/"
)

# ── FAIL PIPELINE IF CRITICAL CHECKS FAIL ─────────────────
if null_dates > 0:
    raise ValueError("CRITICAL FAIL: Null dates in raw data")
if negative_sales > 0:
    raise ValueError("CRITICAL FAIL: Negative sales detected")
if duplicate_dates > 0:
    raise ValueError("CRITICAL FAIL: Duplicate dates found")
if total_records < 100:
    raise ValueError("CRITICAL FAIL: Too few records")

print("=== ALL QUALITY CHECKS PASSED ===")

# ── WRITE 1: Daily Enriched ────────────────────────────────
df.write.mode("overwrite").parquet(
    "s3://pharma-demo-3/processed/daily_enriched/"
)

# ── WRITE 2: Monthly Summary ───────────────────────────────
monthly = df.groupBy("Year", "Month", "Quarter").agg(
    F.round(F.sum("total_daily_sales"), 2).alias("monthly_sales"),
    F.round(F.sum("anti_inflammatory_total"), 2).alias("anti_inflammatory"),
    F.round(F.sum("analgesics_total"), 2).alias("analgesics"),
    F.round(F.sum("cns_drugs_total"), 2).alias("cns_drugs"),
    F.round(F.sum("respiratory_total"), 2).alias("respiratory"),
    F.count("*").alias("trading_days")
).orderBy("Year", "Month")

monthly.write.mode("overwrite").parquet(
    "s3://pharma-demo-3/processed/monthly_summary/"
)

# ── WRITE 3: MoM Trends ────────────────────────────────────
window_mom = Window.orderBy("Year", "Month")
mom = monthly.withColumn(
    "prev_month_sales", F.lag("monthly_sales").over(window_mom)
).withColumn(
    "mom_growth_pct",
    F.round((F.col("monthly_sales") - F.col("prev_month_sales"))
    / F.col("prev_month_sales") * 100, 2)
).withColumn(
    "mom_trend",
    F.when(F.col("mom_growth_pct") < 0, "Declining")
     .when(F.col("mom_growth_pct") >= 10, "Strong Growth")
     .otherwise("Stable")
)

mom.write.mode("overwrite").parquet(
    "s3://pharma-demo-3/processed/mom_trends/"
)

print("ETL complete. 3 tables written to S3.")