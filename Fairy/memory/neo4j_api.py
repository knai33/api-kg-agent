from py2neo import Graph, Node, Relationship, NodeMatcher
import json

graph = Graph("neo4j://localhost:7687", auth=("neo4j", "12345678"))

with open("E:\\agent\\Fairy\\Fairy\\api_files\\output.json", 'r', encoding='utf-8') as f:
    data = json.load(f)

apis = []
for item in data:
    filename = item["filename"]
    for api in item.get("api_list", []):
        apis.append({
            "url": api["url"],
            "method": api["method"],
            "request_content_type": api["request_content_type"],
            "response_content_type": api["response_content_type"],
            "response_body": api["response_body"],
            "post_data": api["post_data"],
            "filename": filename
        })
def create_api_and_page(api):
    # 创建或匹配 Page 节点
    page_node = Node("Page", filename=api["filename"])
    graph.merge(page_node, "Page", "filename")

    # 创建 API 节点
    api_node = Node(
        "API",
        url=api["url"],
        method=api["method"],
        request_content_type=api["request_content_type"],
        response_content_type=api["response_content_type"],
        response_body=api["response_body"],
        post_data=api["post_data"]
    )
    graph.create(api_node)

    # 创建关系
    rel = Relationship(api_node, "RELATED_TO_PAGE", page_node)
    graph.create(rel)

for api in apis:
    create_api_and_page(api)

parameter_dependencies = {
    "roleName": ["roleKey"],  # roleKey 依赖于 roleName
}
def create_parameters_and_dependencies(dependencies):
    for param, deps in dependencies.items():
        p_node = Node("Parameter", name=param)
        graph.merge(p_node, "Parameter", "name")

        for dep in deps:
            d_node = Node("Parameter", name=dep)
            graph.merge(d_node, "Parameter", "name")

            rel = Relationship(d_node, "DEPENDS_ON", p_node)
            graph.create(rel)
create_parameters_and_dependencies(parameter_dependencies)
def create_uses_parameter_relationship(api):
    post_data = api["post_data"]
    if not post_data:
        return

    params = dict(param.split("=") for param in post_data.split("&"))

    for name, value in params.items():
        param_node = Node("Parameter", name=name, value=value)
        graph.merge(param_node, "Parameter", ("name", "value"))

        api_node_matcher = NodeMatcher(graph)
        api_node = api_node_matcher.match(
            "API",
            url=api["url"],
            method=api["method"],
            post_data=post_data
        ).first()

        if api_node:
            rel = Relationship(api_node, "USES_PARAMETER", param_node)
            graph.create(rel)
for api in apis:
    create_uses_parameter_relationship(api)
def create_call_sequence(apis):
    for i in range(len(apis) - 1):
        curr = apis[i]
        next_api = apis[i + 1]

        curr_node = NodeMatcher(graph).match(
            "API",
            url=curr["url"],
            method=curr["method"],
            post_data=curr["post_data"]
        ).first()

        next_node = NodeMatcher(graph).match(
            "API",
            url=next_api["url"],
            method=next_api["method"],
            post_data=next_api["post_data"]
        ).first()

        if curr_node and next_node:
            rel = Relationship(curr_node, "CALLS", next_node)
            graph.create(rel)
create_call_sequence(apis)
