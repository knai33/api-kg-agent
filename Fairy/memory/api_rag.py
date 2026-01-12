from py2neo import Graph, Node, Relationship
from langchain_openai.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.docstore.document import Document
import os

def build_vectorstore(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Chroma:
    # 连接Neo4j数据库
    graph = Graph(neo4j_uri, auth=(neo4j_user, neo4j_password))

    # 查询API请求节点及其关系
    api_query = """
    MATCH (req:APIRequest)
    OPTIONAL MATCH (req)-[rp:HAS_PARAMETER]->(param:Parameter)
    OPTIONAL MATCH (req)-[rr:RETURNS]->(res:APIResponse)
    RETURN 
        req.name AS request_name,
        req.method AS method,
        req.desc AS description,
        req.request_content_type AS content_type,
        COLLECT(DISTINCT {
            relationship: type(rp),
            direction: 'outgoing',
            node: {
                name: param.name, 
                type: param.type, 
                required: param.required, 
                desc: param.desc
            }
        }) AS parameters,
        COLLECT(DISTINCT {
            relationship: type(rr),
            direction: 'outgoing',
            node: {
                name: res.name, 
                desc: res.desc
            }
        }) AS responses
    """

    results = graph.run(api_query).data()

    # 构建文档列表
    documents = []

    for result in results:
        # 构建API请求文档内容
        doc_content = (
            f"API Request: {result['method']} {result['request_name']}\n"
            f"Description: {result['description']}\n"
            f"Content Type: {result['content_type']}\n\n"
        )

        # 添加参数关系信息
        doc_content += "Outgoing Relationships (Parameters):\n"
        for rel in result['parameters']:
            if rel['node']:  # 过滤空参数
                doc_content += (
                    f"- Relationship: {rel['relationship']} (Direction: {rel['direction']})\n"
                    f"  Node Type: Parameter\n"
                    f"  Node Details:\n"
                    f"    Name: {rel['node']['name']}\n"
                    f"    Type: {rel['node']['type']}\n"
                    f"    Required: {rel['node']['required']}\n"
                    f"    Description: {rel['node']['desc']}\n\n"
                )

        # 添加响应关系信息
        doc_content += "Outgoing Relationships (Responses):\n"
        for rel in result['responses']:
            if rel['node']:  # 过滤空响应
                doc_content += (
                    f"- Relationship: {rel['relationship']} (Direction: {rel['direction']})\n"
                    f"  Node Type: Response\n"
                    f"  Node Details:\n"
                    f"    Name: {rel['node']['name']}\n"
                    f"    Description: {rel['node']['desc']}\n\n"
                )

        # 创建文档对象
        doc = Document(
            page_content=doc_content,
            metadata={
                "request_name": result['request_name'],
                "method": result['method'],
                "parameters_count": len([p for p in result['parameters'] if p['node']]),
                "responses_count": len([r for r in result['responses'] if r['node']])
            }
        )
        print(doc)
        documents.append(doc)
    return
    # 创建向量嵌入
    embeddings = OpenAIEmbeddings(
        openai_api_key="sk-8t4sGAakvPVKfFLn9801056499284a66B31aC07b1f9907F3",
        openai_api_base="https://vip.apiyi.com/v1"
    )

    # 创建Chroma向量数据库
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory="./api_vectorstore"
    )

    return vectorstore


# 示例使用
if __name__ == "__main__":
    # 从环境变量获取Neo4j连接信息
    openai_api_key = ""
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "12345678")

    # 构建向量库
    vectorstore = build_vectorstore(uri, user, password)
    #
    # # 示例检索
    # query = "检查角色键是否唯一"
    # results = vectorstore.similarity_search(query, k=2)
    #
    # print(f"查询: {query}")
    # print(f"找到 {len(results)} 个相关API:")
    #
    # for i, doc in enumerate(results, 1):
    #     print(f"\n结果 {i}:")
    #     print(f"API: {doc.metadata['method']} {doc.metadata['request_name']}")
    #     print(f"描述: {doc.page_content.splitlines()[1].split(': ')[1]}")