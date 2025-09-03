[English](oceanbase_mcp_server.md) | 简体中文<br>
# OceanBase MCP Server

OceanBase MCP Server 通过 MCP (模型上下文协议) 可以和 OceanBase 进行交互。
使用支持 MCP 的客户端，连接上 OB 数据库，可以列出所有的表、读取数据以及执行 SQL，然后可以使用大模型对数据库中的数据进一步分析。


## 特性

- 列出所有 OceanBase 数据库中的表作为资源
- 读取表中的数据
- 执行 SQL 语句
- 支持全文查询、向量查询和混合查询
- 通过环境变量访问数据库
- 全面的日志记录

## 工具
- [✔️] 执行 SQL 语句
- [✔️] 查询当前租户
- [✔️] 查询所有的 server 节点信息 （仅支持 sys 租户）
- [✔️] 查询资源信息 （仅支持 sys 租户）
- [✔️] 查询 [ASH](https://www.oceanbase.com/docs/common-oceanbase-database-cn-1000000002013776) 报告
- [✔️] 搜索 OceanBase 官网的文档。
  这个工具是实验性质的，因为官网的 API 接口可能会变化。
- [✔️] 使用全文查询在 OceanBase 中搜索文档
- [✔️] 在 OceanBase 中进行向量查询
- [✔️] 在 OceanBase 中进行向量和标量的混合查询

## 安装

### 克隆仓库
```bash
git clone https://github.com/oceanbase/mcp-oceanbase.git
cd mcp-oceanbase/src/oceanbase_mcp_server
```
如果想使用 pip install 的方式进行安装，请参考 [pip install 安装文档](../src/oceanbase_mcp_server/README_CN.md)
### 安装 Python 包管理器 uv 并创建虚拟环境
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate  # 在Windows系统上执行 `.venv\Scripts\activate`
```
### 如果使用 .env 文件配置 OceanBase 的连接信息，需要复制 .env.template 文件为 .env，然后修改 .env 文件
```bash
cp .env.template .env
```
### 如果因为网络问题 uv 下载文件较慢或者无法下载，可以使用阿里云的镜像源
```bash
export UV_DEFAULT_INDEX="https://mirrors.aliyun.com/pypi/simple/"
```
### 安装依赖
```bash
uv pip install .
```
## 配置
有两种方式可以配置 OceanBase 的连接信息
1. 在环境变量中设置以下变量的值：
```bash
OB_HOST=localhost     # 数据库的地址
OB_PORT=2881         # 可选的数据库的端口（如果没有配置，默认是2881)
OB_USER=your_username
OB_PASSWORD=your_password
OB_DATABASE=your_database
```
2. 在 .env 文件中进行配置
## 使用方法

### stdio 模式
在支持 MCP 的客户端中，将下面的内容填入配置文件，请根据实际信息修改
```json
{
  "mcpServers": {
    "oceanbase": {
      "command": "uv",
      "args": [
        "--directory", 
        "path/to/mcp-oceanbase/src/oceanbase_mcp_server",
        "run",
        "oceanbase_mcp_server"
      ],
      "env": {
        "OB_HOST": "localhost",
        "OB_PORT": "2881",
        "OB_USER": "your_username",
        "OB_PASSWORD": "your_password",
        "OB_DATABASE": "your_database"
      }
    }
  }
}
```
### sse 模式
在 mcp-oceanbase/src/oceanbase_mcp_server 目录下，执行下面的命令，端口号是可配置的。<br>
'--transport'： MCP 的传输模式，stdio 或者 sse，默认是 stdio<br>
'--host'： sse 模式绑定的 host，默认是 127.0.0.1，也就是只能本机访问，如果需要远程访问，可以设置为 0.0.0.0<br>
'--port'： sse 模式监听的端口，默认是 8000
```bash
uv run oceanbase_mcp_server --transport sse --port 8000
```
如果不想使用 uv，也可以用下面的方式启动
```bash
cd oceanbase_mcp/ && python3 -m server --transport sse --port 8000
```
sse 模式访问地址示例： `http://ip:port/sse`
## 示例
### 例子 1: 列出所有的表
问题：
```plaintext
How many tables are there in the test database, and what are they?
```
答案：
```plaintext
Tables in test: 
t1
t2
```
### Example 2: 查看当前租户
问题：
```
What is my current tenant name?
```
答案：
```
Your current tenant name is 'sys'.
```
### 例子 3: 查看所有的 server 节点
You need to be sys tenant to get all server nodes.
问题：
```
Query all server nodes
```
答案：
```
Successfully queried all server nodes. Here are the details:

| SVR_IP   | SVR_PORT | ID | ZONE  | SQL_PORT | WITH_ROOTSERVER | STATUS | START_SERVICE_TIME        | STOP_TIME | BLOCK_MIGRATE_IN_TIME | CREATE_TIME            | MODIFY_TIME            | BUILD_VERSION                                                                 | LAST_OFFLINE_TIME |
|----------|----------|----|-------|----------|-----------------|--------|---------------------------|-----------|-----------------------|-------------------------|-------------------------|------------------------------------------------------------------------------|-------------------|
| 127.0.0.1 | 2882     | 1  | zone1 | 2881     | YES             | ACTIVE | 2024-06-27 15:40:19.003123 | None      | None                  | 2024-06-19 16:39:11.749421 | 2024-06-27 15:40:21.001573 | 4.2.3.1_101000012024061216-c436ab3557c826ab31931d11ec836dc4df09d9de(Jun 12 2024 16:25:30) | None              |

This table provides comprehensive information about each server node, including IP addresses, ports, zones, statuses, and timestamps.
```
### 例子 4: 查看资源容量
你需要是 sys 租户，才可以查询资源容量
问题：
```
Query the current resource capacity information
```
答案：
```
The current resource capacity information has been successfully queried. Here are the details:

| SVR_IP   | SVR_PORT | ZONE  | SQL_PORT | CPU_CAPACITY | CPU_CAPACITY_MAX | CPU_ASSIGNED | CPU_ASSIGNED_MAX | MEM_CAPACITY | MEM_ASSIGNED | LOG_DISK_CAPACITY | LOG_DISK_ASSIGNED | LOG_DISK_IN_USE | DATA_DISK_CAPACITY | DATA_DISK_IN_USE | DATA_DISK_HEALTH_STATUS | MEMORY_LIMIT | DATA_DISK_ALLOCATED | DATA_DISK_ABNORMAL_TIME | SSL_CERT_EXPIRED_TIME |
|----------|----------|-------|----------|--------------|------------------|--------------|------------------|--------------|--------------|-------------------|-------------------|-----------------|--------------------|-----------------|-------------------------|--------------|---------------------|-------------------------|-----------------------|
| 127.0.0.1 | 2882     | zone1 | 2881     | 4            | 4.0              | 2.0          | 2.0              | 5368709120    | 3221225472    | 5368709120         | 4294967296         | 3556769792       | 10737418240        | 664797184        | NORMAL                  | 6442450944    | 10737418240         | None                    | None                  |

This table provides comprehensive information about the resource capacities and assignments for the server.
```
### 例子 5: 拿到 ASH 报告
拿到 OceanBase Active Session History 报告.  
Question：
```
Please provide me with today's ASH report.
```
Answer：
```
The ASH report for today (2025-09-03) has been successfully generated. Key findings include:

Cluster Overview:
- Name: ob6u2klmn4pwo0
- Observer Version: OceanBase 4.3.5.2
- OS: Linux(5.10.134-17.2.al8.x86_64)_x86_64
- Analysis period: 2025-09-03 00:00:00 to 2025-09-03 11:26:40
- Average Active Sessions: 0.45

Top Activity:
1. Tenant t6wxyssara4e8 dominated background activity (99.99%)
2. Nodes 10.102.32.82, 10.102.64.254, and 10.102.49.151 showed highest activity
3. Primary activities:
   - TenantWeakReadService generating cluster versions
   - LogService I/O operations
   - TimerWK background tasks
   - LSRecoveryService reporting

Resource Utilization:
- Main wait events: exec inner sql wait (various), palf write, sync rpc
- Top IO operations: COMPACTION tasks (TX_TABLE_MERGE, MINI_MERGE)
- Primary SQL activity: SELECT statements (17.36% of activity)

The complete report contains detailed breakdowns of:
- Node-specific activity
- IO bandwidth usage
- Latch waits
- Object access patterns
- Execution phases
- SQL execution statistics

Would you like me to extract or highlight any specific sections of the report?
```
### 例子 6: 使用全文查询检索文档
问题：
```
Find content in t2 table that mention "apple"
```
答案：
```
I have successfully queried the documents in the content field of table t2 that mention "apple". Here are the results:

1. Document ID: 2, Author: john, Age: 20, Content: I have a pear and an apple
2. Document ID: 1, Author: david, Age: 19, Content: I have a pineapple and an apple
3. Document ID: 3, Author: tom, Age: 21, Content: I also have a pear and an apple
```
### Example 7: 向量查询
问题：
```
Please search for records in table t2 that are close to the vector [0.1, 0.1, 0.1].
```
答案：
```
The vector search on table t2 has returned results successfully. I can now analyze and present these results to the user.

The search found three records that are close to the vector [0.1, 0.1, 0.1]:

1. Record with id 2, name 'john', age 20, description 'I have a pear and an apple', vector '[0.1,0.1,0.2]', and distance 0.1
2. Record with id 3, name 'tom', age 21, description 'I also have a pear and an apple', vector '[0.1,0.1,0.2]', and distance 0.1
3. Record with id 1, name 'david', age 19, description 'I have a pineapple and an apple', vector '[0.1,0.2,0.3]', and distance 0.2236

These records are ordered by their distance from the search vector, with closer matches appearing first.
```
### 例子 8: 混合查询
Perform hybird search combining relational condition filtering(that is, scalar) and vector search. 
进行关系条件过滤（即标量）和向量的混合查询 
问题：
```
Please find the record in table t2 that has a vector close to [0.1, 0.1, 0.2] and an age of 20.
```
Using both vectors and scalars as query conditions.  
答案：
```
The record in table `t2` that has a vector close to `[0.1, 0.1, 0.2]` and an age of 20 is:
(2, 'john', 20, 'I have a pear and an apple', '[0.1,0.1,0.2]', 0.0)
```
## 安全注意事项
- 不要提交环境变量信息或者凭证
- 使用最小权限的数据库用户
- 对于生产环境，考虑设置查询白名单
- 监控并记录所有的数据库操作

## 安全最佳实践
MCP 中的工具会访问数据库，为了安全：
1. **创建一个专用的 OceanBase 用户**，拥有最小的权限
2. **不要使用 root 用户**
3. **限制数据库的操作**，只运行必要的操作
4. **开启日志记录**，以便进行审计
5. **进行数据库访问的日常巡检**

## 许可证

Apache License - 查看 LICENSE 文件获取细节。

## 贡献

1. Fork 这个仓库
2. 创建你自己的分支 （`git checkout -b feature/amazing-feature`）
3. 提交修改 （`git commit -m 'Add some amazing feature'`）
4. 推送到远程仓库 （`git push origin feature/amazing-feature`）
5. 提交 PR