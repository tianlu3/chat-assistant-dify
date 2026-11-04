import os
import pymysql
import pandas as pd

# 1. 建立数据库连接
connection = pymysql.connect(
    host=os.getenv('DB_HOST', '127.0.0.1'),
    user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD', 'your-password'),
    database=os.getenv('DB_NAME', 'chat'),
    charset='utf8mb4'
)

try:
    # 2. 使用 Pandas 直接读取 SQL 数据存入 DataFrame
    query = "SELECT * FROM records;"
    df = pd.read_sql(query, connection)

    # 3. 打印查看结果
    print(df.head())
    print(f"数据读取成功，共 {len(df)} 条记录。")

except Exception as e:
    print(f"发生错误: {e}")

finally:
    # 4. 关闭连接
    connection.close()