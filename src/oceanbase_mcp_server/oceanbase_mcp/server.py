from __future__ import annotations
import logging
import os
import time
from typing import Optional, List
from urllib import request, error
import json
import argparse
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mysql.connector import Error, connect
from bs4 import BeautifulSoup
import certifi
import ssl
from pydantic import BaseModel
from pyobvector import ObVecClient, MatchAgainst, l2_distance, inner_product, cosine_distance
from sqlalchemy import text
import ast

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("oceanbase_mcp_server")

load_dotenv()

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-en-v1.5")
EMBEDDING_MODEL_PROVIDER = os.getenv("EMBEDDING_MODEL_PROVIDER", "huggingface")
ENABLE_MEMORY = int(os.getenv("ENABLE_MEMORY", 0))

TABLE_NAME_MEMORY = os.getenv("TABLE_NAME_MEMORY", "ob_mcp_memory")

logger.info(
    f" ENABLE_MEMORY: {ENABLE_MEMORY},EMBEDDING_MODEL_NAME: {EMBEDDING_MODEL_NAME}, EMBEDDING_MODEL_PROVIDER: {EMBEDDING_MODEL_PROVIDER}"
)


class OBConnection(BaseModel):
    host: str
    port: int
    user: str
    password: str
    database: str


class OBMemoryItem(BaseModel):
    mem_id: int = None
    content: str
    meta: dict
    embedding: List[float]


# Check if authentication should be enabled based on ALLOWED_TOKENS
# This check happens after load_dotenv() so it can read from .env file
allowed_tokens_str = os.getenv("ALLOWED_TOKENS", "")
enable_auth = bool(allowed_tokens_str.strip())


class SimpleTokenVerifier(TokenVerifier):
    """
    Simple token verifier that validates tokens against a list of allowed tokens.
    Configure allowed tokens via ALLOWED_TOKENS environment variable (comma-separated).
    """

    def __init__(self):
        # Get allowed tokens from environment variable
        allowed_tokens_str = os.getenv("ALLOWED_TOKENS", "")
        self.allowed_tokens = set(
            token.strip() for token in allowed_tokens_str.split(",") if token.strip()
        )

        logger.info(f"Token verifier initialized with {len(self.allowed_tokens)} allowed tokens")

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Verify a bearer token.

        Args:
            token: The token to verify

        Returns:
            AccessToken if valid, None if invalid
        """
        # Check if token is empty
        if not token or not token.strip():
            logger.debug("Empty token provided")
            return None

        # Check if token is in allowed list
        if token not in self.allowed_tokens:
            logger.warning(f"Invalid token provided: {token[:10]}...")
            return None

        logger.debug(f"Valid token accepted: {token[:10]}...")
        return AccessToken(
            token=token, client_id="authenticated_client", scopes=["read", "write"], expires_at=None
        )


db_conn_info = OBConnection(
    host=os.getenv("OB_HOST", "localhost"),
    port=os.getenv("OB_PORT", 2881),
    user=os.getenv("OB_USER"),
    password=os.getenv("OB_PASSWORD"),
    database=os.getenv("OB_DATABASE"),
)

if enable_auth:
    logger.info("Authentication enabled - ALLOWED_TOKENS configured")
    # Initialize server with token verifier and minimal auth settings
    # FastMCP requires auth settings when using token_verifier
    app = FastMCP(
        "oceanbase_mcp_server",
        token_verifier=SimpleTokenVerifier(),
        auth=AuthSettings(
            # Because the TokenVerifier is being used, the following two URLs only need to comply with the URL rules.
            issuer_url="http://localhost:8000",
            resource_server_url="http://localhost:8000",
        ),
    )
else:
    # Initialize server without authentication
    app = FastMCP("oceanbase_mcp_server")


@app.resource("oceanbase://sample/{table}", description="table sample")
def table_sample(table: str) -> str:
    try:
        with connect(**db_conn_info.model_dump()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM `%s` LIMIT 100", params=(table,))
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = [",".join(map(str, row)) for row in rows]
                return "\n".join([",".join(columns)] + result)

    except Error:
        return f"Failed to sample table: {table}"


@app.resource("oceanbase://tables", description="list all tables")
def list_tables() -> str:
    """List OceanBase tables as resources."""
    try:
        with connect(**db_conn_info.model_dump()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                logger.info(f"Found tables: {tables}")
                resp_header = "Tables of this table: \n"
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                result = [",".join(map(str, row)) for row in rows]
                return resp_header + ("\n".join([",".join(columns)] + result))
    except Error as e:
        logger.error(f"Failed to list tables: {str(e)}")
        return "Failed to list tables"


@app.tool()
def execute_sql(sql: str) -> str:
    """Execute an SQL on the OceanBase server."""
    logger.info(f"Calling tool: execute_sql  with arguments: {sql}")

    try:
        with connect(**db_conn_info.model_dump()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)

                # Special handling for SHOW TABLES
                if sql.strip().upper().startswith("SHOW TABLES"):
                    tables = cursor.fetchall()
                    result = [f"Tables in {db_conn_info.database}: "]  # Header
                    result.extend([table[0] for table in tables])
                    return "\n".join(result)

                elif sql.strip().upper().startswith("SHOW COLUMNS"):
                    resp_header = "Columns info of this table: \n"
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    result = [",".join(map(str, row)) for row in rows]
                    return resp_header + ("\n".join([",".join(columns)] + result))

                elif sql.strip().upper().startswith("DESCRIBE"):
                    resp_header = "Description of this table: \n"
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    result = [",".join(map(str, row)) for row in rows]
                    return resp_header + ("\n".join([",".join(columns)] + result))

                # Regular SELECT queries
                elif sql.strip().upper().startswith("SELECT"):
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    result = [",".join(map(str, row)) for row in rows]
                    return "\n".join([",".join(columns)] + result)

                # Regular SHOW queries
                elif sql.strip().upper().startswith("SHOW"):
                    rows = cursor.fetchall()
                    return rows
                # process procedural invoke
                elif sql.strip().upper().startswith("CALL"):
                    rows = cursor.fetchall()
                    if not rows:
                        return "No result return."
                    # the first column contains the report text
                    return rows[0]
                # Non-SELECT queries
                else:
                    conn.commit()
                    return f"Sql executed successfully. Rows affected: {cursor.rowcount}"

    except Error as e:
        logger.error(f"Error executing SQL '{sql}': {e}")
        return f"Error executing sql: {str(e)}"


@app.tool()
def get_ob_ash_report(
    start_time: str,
    end_time: str,
    tenant_id: Optional[str] = None,
) -> str:
    """
    Get OceanBase Active Session History report.
    ASH can sample the status of all Active Sessions in the system at 1-second intervals, including:
        Current executing SQL ID
        Current wait events (if any)
        Wait time and wait parameters
        The module where the SESSION is located during sampling (PARSE, EXECUTE, PL, etc.)
        SESSION status records, such as SESSION MODULE, ACTION, CLIENT ID
    This will be very useful when you perform performance analysis.RetryClaude can make mistakes. Please double-check responses.

    Args:
        start_time: Sample Start Time,Format: yyyy-MM-dd HH:mm:ss.
        end_time: Sample End Time,Format: yyyy-MM-dd HH:mm:ss.
        tenant_id: Used to specify the tenant ID for generating the ASH Report. Leaving this field blank or setting it to NULL indicates no restriction on the TENANT_ID.
    """
    logger.info(
        f"Calling tool: get_ob_ash_report  with arguments: {start_time}, {end_time}, {tenant_id}"
    )
    if tenant_id is None:
        tenant_id = "NULL"
    # Construct the SQL query
    sql_query = f"""
        CALL DBMS_WORKLOAD_REPOSITORY.ASH_REPORT('{start_time}','{end_time}', NULL, NULL, NULL, 'TEXT', NULL, NULL, {tenant_id});
    """
    try:
        result = execute_sql(sql_query)
        logger.info(f"ASH report result: {result}")
        return result
    except Error as e:
        logger.error(f"Error get ASH report,executing SQL '{sql_query}': {e}")
        return f"Error get ASH report,{str(e)}"


@app.tool(name="get_current_time", description="Get current time")
def get_current_time() -> str:
    local_time = time.localtime()
    formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    logger.info(f"Current time: {formatted_time}")
    return formatted_time


@app.tool()
def get_current_tenant() -> str:
    """
    Get the current tenant name from oceanbase.
    """
    logger.info("Calling tool: get_current_tenant")
    sql_query = "show tenant"
    try:
        result = ast.literal_eval(execute_sql(sql_query))
        logger.info(f"Current tenant: {result}")
        return result[0][0]
    except Error as e:
        logger.error(f"Error executing SQL '{sql_query}': {e}")
        return f"Error executing query: {str(e)}"


@app.tool()
def get_all_server_nodes():
    """
    Get all server nodes from oceanbase.
    You need to be sys tenant to get all server nodes.
    """
    tenant = get_current_tenant()
    if tenant != "sys":
        raise ValueError("Only sys tenant can get all server nodes")

    logger.info("Calling tool: get_all_server_nodes")
    sql_query = "select * from oceanbase.DBA_OB_SERVERS"
    try:
        return execute_sql(sql_query)
    except Error as e:
        logger.error(f"Error executing SQL '{sql_query}': {e}")
        return f"Error executing query: {str(e)}"


@app.tool()
def get_resource_capacity():
    """
    Get resource capacity from oceanbase.
    You need to be sys tenant to get resource capacity.
    """
    tenant = get_current_tenant()
    if tenant != "sys":
        raise ValueError("Only sys tenant can get resource capacity")
    logger.info("Calling tool: get_resource_capacity")
    sql_query = "select * from oceanbase.GV$OB_SERVERS"
    try:
        return execute_sql(sql_query)
    except Error as e:
        logger.error(f"Error executing SQL '{sql_query}': {e}")
        return f"Error executing query: {str(e)}"


@app.tool()
def search_oceanbase_document(keyword: str) -> str:
    """
    This tool is designed to provide context-specific information about OceanBase to a large language model (LLM) to enhance the accuracy and relevance of its responses.
    The LLM should automatically extracts relevant search keywords from user queries or LLM's answer for the tool parameter "keyword".
    The main functions of this tool include:
    1.Information Retrieval: The MCP Tool searches through OceanBase-related documentation using the extracted keywords, locating and extracting the most relevant information.
    2.Context Provision: The retrieved information from OceanBase documentation is then fed back to the LLM as contextual reference material. This context is not directly shown to the user but is used to refine and inform the LLM’s responses.
    This tool ensures that when the LLM’s internal documentation is insufficient to generate high-quality responses, it dynamically retrieves necessary OceanBase information, thereby maintaining a high level of response accuracy and expertise.
    """
    logger.info(f"Calling tool: search_oceanbase_document,keyword:{keyword}")
    search_api_url = (
        "https://cn-wan-api.oceanbase.com/wanApi/forum/docCenter/productDocFile/v3/searchDocList"
    )
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.oceanbase.com",
        "Referer": "https://www.oceanbase.com/",
    }
    qeury_param = {
        "pageNo": 1,
        "pageSize": 5,  # Search for 5 results at a time.
        "query": keyword,
    }
    # Turn the dictionary into a JSON string, then change it to bytes
    qeury_param = json.dumps(qeury_param).encode("utf-8")
    req = request.Request(search_api_url, data=qeury_param, headers=headers, method="POST")
    # Create an SSL context using certifi to fix HTTPS errors.
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with request.urlopen(req, timeout=5, context=context) as response:
            response_body = response.read().decode("utf-8")
            json_data = json.loads(response_body)
            # In the results, we mainly need the content in the data field.
            data_array = json_data["data"]  # Parse JSON response
            result_list = []
            for item in data_array:
                doc_url = "https://www.oceanbase.com/docs/" + item["urlCode"] + "-" + item["id"]
                logger.info(f"doc_url:${doc_url}")
                content = get_ob_doc_content(doc_url, item["id"])
                result_list.append(content)
            return json.dumps(result_list, ensure_ascii=False)
    except error.HTTPError as e:
        logger.error(f"HTTP Error: {e.code} - {e.reason}")
        return "No results were found"
    except error.URLError as e:
        logger.error(f"URL Error: {e.reason}")
        return "No results were found"


def get_ob_doc_content(doc_url: str, doc_id: str) -> dict:
    doc_param = {"id": doc_id, "url": doc_url}
    doc_param = json.dumps(doc_param).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.oceanbase.com",
        "Referer": "https://www.oceanbase.com/",
    }
    doc_api_url = (
        "https://cn-wan-api.oceanbase.com/wanApi/forum/docCenter/productDocFile/v4/docDetails"
    )
    req = request.Request(doc_api_url, data=doc_param, headers=headers, method="POST")
    # Make an SSL context with certifi to fix HTTPS errors.
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with request.urlopen(req, timeout=5, context=context) as response:
            response_body = response.read().decode("utf-8")
            json_data = json.loads(response_body)
            # In the results, we mainly need the content in the data field.
            data = json_data["data"]
            # The docContent field has HTML text.
            soup = BeautifulSoup(data["docContent"], "html.parser")
            # Remove script, style, nav, header, and footer elements.
            for element in soup(["script", "style", "nav", "header", "footer"]):
                element.decompose()
            # Remove HTML tags and keep only the text.
            text = soup.get_text()
            # Remove spaces at the beginning and end of each line.
            lines = (line.strip() for line in text.splitlines())
            # Remove empty lines.
            text = "\n".join(line for line in lines if line)
            logger.info(f"text length:{len(text)}")
            # If the text is too long, only keep the first 8000 characters.
            if len(text) > 8000:
                text = text[:8000] + "... [content truncated]"
            # Reorganize the final result. The tdkInfo field should include the document's title, description, and keywords.
            tdkInfo = data["tdkInfo"]
            final_result = {
                "title": tdkInfo["title"],
                "description": tdkInfo["description"],
                "keyword": tdkInfo["keyword"],
                "content": text,
                "oceanbase_version": data["version"],
                "content_updatetime": data["docGmtModified"],
            }
            return final_result
    except error.HTTPError as e:
        logger.error(f"HTTP Error: {e.code} - {e.reason}")
        return {"result": "No results were found"}
    except error.URLError as e:
        logger.error(f"URL Error: {e.reason}")
        return {"result": "No results were found"}


@app.tool()
def oceanbase_text_search(
    table_name: str,
    full_text_search_column_name: list[str],
    full_text_search_expr: str,
    other_where_clause: Optional[list[str]] = None,
    limit: int = 5,
    output_column_name: Optional[list[str]] = None,
) -> str:
    """
    Search for documents using full text search in an OceanBase table.

    Args:
        table_name: Name of the table to search.
        full_text_search_column_name: Specify the columns to be searched in full text.
        full_text_search_expr: Specify the keywords or phrases to search for.
        other_where_clause: Other WHERE condition query statements except full-text search.
        limit: Maximum number of results to return.
        output_column_name: columns to include in results.
    """
    logger.info(
        f"Calling tool: oceanbase_text_search  with arguments: {table_name}, {full_text_search_column_name}, {full_text_search_expr}"
    )
    client = ObVecClient(
        uri=db_conn_info.host + ":" + str(db_conn_info.port),
        user=db_conn_info.user,
        password=db_conn_info.password,
        db_name=db_conn_info.database,
    )
    where_clause = [MatchAgainst(full_text_search_expr, *full_text_search_column_name)]
    for item in other_where_clause or []:
        where_clause.append(text(item))
    results = client.get(
        table_name=table_name,
        ids=None,
        where_clause=where_clause,
        output_column_name=output_column_name,
        n_limits=limit,
    )
    output = f"Search results for '{full_text_search_expr}'"
    if other_where_clause:
        output += " and " + ",".join(other_where_clause)
    output += f" in table '{table_name}':\n\n"
    for result in results:
        output += str(result) + "\n\n"
    return output


@app.tool()
def oceabase_vector_search(
    table_name: str,
    vector_data: list[float],
    vec_column_name: str = "vector",
    distance_func: Optional[str] = "l2",
    with_distance: Optional[bool] = True,
    topk: int = 5,
    output_column_name: Optional[list[str]] = None,
) -> str:
    """
    Perform vector similarity search on an OceanBase table.

    Args:
        table_name: Name of the table to search.
        vector_data: Query vector.
        vec_column_name: column name containing vectors to search.
        distance_func: The index distance algorithm used when comparing the distance between two vectors.
        with_distance: Whether to output distance data.
        topk: Number of results returned.
        output_column_name: Returned table fields.
    """
    logger.info(
        f"Calling tool: oceabase_vector_search  with arguments: {table_name}, {vector_data[:10]}, {vec_column_name}"
    )
    client = ObVecClient(
        uri=db_conn_info.host + ":" + str(db_conn_info.port),
        user=db_conn_info.user,
        password=db_conn_info.password,
        db_name=db_conn_info.database,
    )
    match distance_func:
        case "l2":
            search_distance_func = l2_distance
        case "inner product":
            search_distance_func = inner_product
        case "cosine":
            search_distance_func = cosine_distance
        case _:
            raise ValueError("Unkown distance function")

    results = client.ann_search(
        table_name=table_name,
        vec_data=vector_data,
        vec_column_name=vec_column_name,
        distance_func=search_distance_func,
        with_dist=with_distance,
        topk=topk,
        output_column_names=output_column_name,
    )
    output = f"Vector search results for '{table_name}:\n\n'"
    for result in results:
        output += str(result) + "\n\n"
    return output


@app.tool()
def oceanbase_hybrid_search(
    table_name: str,
    vector_data: list[float],
    vec_column_name: str = "vector",
    distance_func: Optional[str] = "l2",
    with_distance: Optional[bool] = True,
    filter_expr: Optional[list[str]] = None,
    topk: int = 5,
    output_column_name: Optional[list[str]] = None,
) -> str:
    """
    Perform hybird search combining relational condition filtering(that is, scalar) and vector search.

    Args:
        table_name: Name of the table to search.
        vector_data: Query vector.
        vec_column_name: column name containing vectors to search.
        distance_func: The index distance algorithm used when comparing the distance between two vectors.
        with_distance: Whether to output distance data.
        filter_expr: Scalar conditions requiring filtering in where clause.
        topk: Number of results returned.
        output_column_name: Returned table fields,unless explicitly requested, please do not provide.
    """
    logger.info(
        f"""Calling tool: oceanbase_hybrid_search  with arguments: {table_name}, {vector_data[:10]}, {vec_column_name}
        ,{filter_expr}"""
    )
    client = ObVecClient(
        uri=db_conn_info.host + ":" + str(db_conn_info.port),
        user=db_conn_info.user,
        password=db_conn_info.password,
        db_name=db_conn_info.database,
    )
    match distance_func.lower():
        case "l2":
            search_distance_func = l2_distance
        case "inner product":
            search_distance_func = inner_product
        case "cosine":
            search_distance_func = cosine_distance
        case _:
            raise ValueError("Unkown distance function")
    where_clause = []
    for item in filter_expr or []:
        where_clause.append(text(item))
    results = client.ann_search(
        table_name=table_name,
        vec_data=vector_data,
        vec_column_name=vec_column_name,
        distance_func=search_distance_func,
        with_dist=with_distance,
        where_clause=where_clause,
        topk=topk,
        output_column_names=output_column_name,
    )
    output = f"Hybrid search results for '{table_name}:\n\n'"
    for result in results:
        output += str(result) + "\n\n"
    return output


if ENABLE_MEMORY:
    from pyobvector import ObVecClient, l2_distance, VECTOR
    from sqlalchemy import Column, Integer, JSON, String, text

    class OBMemory:
        def __init__(self):
            self.embedding_client = self._gen_embedding_client()
            self.embedding_dimension = len(self.embedding_client.embed_query("test"))
            logger.info(f"embedding_dimension: {self.embedding_dimension}")

            self.client = ObVecClient(
                uri=db_conn_info.host + ":" + str(db_conn_info.port),
                user=db_conn_info.user,
                password=db_conn_info.password,
                db_name=db_conn_info.database,
            )
            self._init_obvector()

        def gen_embedding(self, text: str) -> List[float]:
            return self.embedding_client.embed_query(text)

        def _gen_embedding_client(self):
            """
            Generate embedding cient.
            """
            if EMBEDDING_MODEL_PROVIDER == "huggingface":
                os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                from langchain_huggingface import HuggingFaceEmbeddings

                logger.info(f"Using HuggingFaceEmbeddings model: {EMBEDDING_MODEL_NAME}")
                return HuggingFaceEmbeddings(
                    model_name=EMBEDDING_MODEL_NAME,
                    encode_kwargs={"normalize_embeddings": True},
                )
            else:
                raise ValueError(
                    f"Unsupported embedding model provider: {EMBEDDING_MODEL_PROVIDER}"
                )

        def _init_obvector(self):
            """
            Initialize the OBVector.
            """
            client = ObVecClient(
                uri=db_conn_info.host + ":" + str(db_conn_info.port),
                user=db_conn_info.user,
                password=db_conn_info.password,
                db_name=db_conn_info.database,
            )
            if not client.check_table_exists(TABLE_NAME_MEMORY):
                # Get embedding dimension dynamically from model config
                cols = [
                    Column("mem_id", Integer, primary_key=True, autoincrement=True),
                    Column("content", String(8000)),
                    Column("embedding", VECTOR(self.embedding_dimension)),
                    Column("meta", JSON),
                ]
                client.create_table(TABLE_NAME_MEMORY, columns=cols)

                # create vector index
                client.create_index(
                    TABLE_NAME_MEMORY,
                    is_vec_index=True,
                    index_name="vidx",
                    column_names=["embedding"],
                    vidx_params="distance=l2, type=hnsw, lib=vsag",
                )

    ob_memory = OBMemory()

    def ob_memory_insert(content: str):
        """
        Purpose: Instantly capture and store any personal facts the user volunteers in the conversation.

        Trigger rule:
        Call this tool every single time the user mentions anything about themselves, no matter how trivial or indirectly stated.

        Personal facts include (non-exhaustive):

        Demographics: age, gender, date of birth, nationality, hometown
        Work & education: current / past job titles, industries, schools, degrees, skills
        Geography & time: city of residence, frequent locations, travel history, time-zone
        Preferences & aversions: foods, music, movies, books, brands, colors, hobbies
        Lifestyle details: pets, family members, daily habits, languages, beliefs
        Experiences & achievements: awards, projects, certificates, key life events

        Guidelines for the model:
        Invoke ob_memory_insert immediately whenever any personal fact appears in the user’s message.
        Extract every distinct fact present in the same utterance; list them all.
        Use the exact user wording in the quote field to preserve context.
        Args:
            content: summary of the facts stated by the user, JSON format like shown below
            {
            "facts": [
            {
            "type": "occupation",
            "value": "product manager",
            "quote": "I've been a product manager for five years"
            },
            {
            "type": "preference",
            "value": "unsweetened latte",
            "quote": "I need an unsweetened latte every morning"
            }
           ]
        }
        """
        print('content:',content)
        return "Inserted successfully"
    def ob_memory_query(intent: str,filters:str, topk: int = 5) -> str:
        """
        Purpose: Look up any stored personal facts about the user before composing an answer.
        When to call:
        Invoke this tool whenever the upcoming response could be made more accurate, relevant, or personalized by knowing the user’s stored details. Typical triggers include questions or statements that touch on:
        • recommendations (food, travel, products, media)
        • advice based on age, location, profession, or experience
        • cultural, linguistic
        • any topic where the user’s preferences, demographics, or past events matter
        Args:
            intent: "concise description of what the answer needs"
            filters: "occupation, location, preferences, demographics"
        intent: 1–2 phrases summarizing the information you are about to generate (e.g., “weekend travel plan” or “birthday gift idea”)
        filters: list only the fact categories that are plausibly useful for this intent; leave empty if a broad recall is needed.
        """
    def ob_memory_update(mem_id: int, content: str, meta: dict):
        """
        Purpose: Overwrite or retire any previously stored personal fact when the user explicitly states a change, correction, or removal of that fact.
        Trigger rule: 
            Call this tool immediately when the user expresses:
            • A new preference that replaces an old one (“I used to love apples, but now I prefer pears.”)
            • A change of status or location (“I just moved from Shanghai to Hangzhou.”)
            • A correction (“Actually, I’m 31, not 30.”)
            • A wish to delete a previously recorded fact (“Please forget that I said I hate jazz.”)
        Args:
            mem_id: memory ID retrieved from the database of the outdated fact
            content: JSON format like show below
            {
            "old_value": "apple",        // exact or paraphrased text of the outdated fact
            "new_value": "pear",         // the updated value; use null for deletion
            "type": "preference",
            "quote": "I used to love apples, but now I prefer pears."
            }
        • old_value: the previously stored value (use the exact string if you have it; otherwise the closest paraphrase).
        • new_value: the new value to store; set to null when the fact should be removed entirely.
        • type: one of the standard fact types (preference, location, age, occupation, etc.).
        • quote: the user’s literal statement capturing the change.
        Example invocations:
            User: “I’ve switched from iOS to Android.”
            {
            "old_value": "iOS",
            "new_value": "Android",
            "type": "preference",
            "quote": "I've switched from iOS to Android."
            }
            User: “I don’t actually dislike dogs.”
            {
            "old_value": "dislikes dogs",
            "new_value": null,
            "type": "preference",
            "quote": "I don't actually dislike dogs."
            }
        Guideline for the model:
        Whenever you detect a temporal cue (now, currently, these days, recently, since, used to) or an explicit contradiction of a stored fact, invoke update_user_fact before giving any further response.
        """
    app.add_tool(ob_memory_insert)


def main():
    """Main entry point to run the MCP server."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transport",
        type=str,
        default="stdio",
        help="Specify the MCP server transport type as stdio or sse or streamable-http.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()
    transport = args.transport
    logger.info(f"Starting OceanBase MCP server with {transport} mode...")
    if transport in {"sse", "streamable-http"}:
        app.settings.host = args.host
        app.settings.port = args.port
    app.run(transport=transport)


if __name__ == "__main__":
    main()
