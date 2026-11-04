from fastmcp import FastMCP
import os
import pymysql

#服务器标识符、mcp服务名、端口号
mcp_server = FastMCP()

#连接数据库
def connect_to_database():
    try:
        config = {
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", "your-password"),
            "host": os.getenv("DB_HOST", "127.0.0.1"),
            "database": os.getenv("DB_NAME", "wechat"),
        }
        conn = pymysql.connect(**config)
        print("Connected to MySQL database")
        return conn
    except pymysql.Error as err:
        print(F"Error: {err}")
        return None


# 执行SQL查询
def execute_query(conn, sql):
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        if sql.strip().lower().startswith("select"):

            # 如果是查询操作，返回结果
            result = cursor.fetchall()
            return result
        else:
            # 如果是插入、更新、删除操作，提交事务并返回受影响的行数
            conn.commit()
            return cursor.rowcount
    except pymysql.Error as err:
        print(f"Error executing SQL: {err}")
        return None
    finally:
        cursor.close()


@mcp_server.tool(name="execute_sqlstatement", description="Execute SQL on MySQL")
def execute_sql(sql: str) -> str:
    conn = connect_to_database()
    if not conn:
        return "Failed to connect to database"
    # 执行SQL
    result = execute_query(conn, sql)
    conn.close()

    if result is None:
        return "Failed to execute SQL"
    # 返回结果
    return result.__str__()


if __name__ == "__main__":
    mcp_server.run(host="0.0.0.0", port=8095, transport="sse")  # 启动 SSE 服务