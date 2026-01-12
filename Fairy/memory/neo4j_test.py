import json

import py2neo
from py2neo import Graph, Node, Relationship, NodeMatcher, RelationshipMatcher
from urllib.parse import urlparse, parse_qs, unquote
import os


class ApiDataParser:
    def __init__(self, uri, user, password, database="neo4j", clear_existing=False):
        # 指定要连接的数据库
        self.graph = Graph(uri, auth=(user, password), database=database)
        if clear_existing:
            self.clear_database()

    def clear_database(self):
        """清空数据库中的所有数据"""
        self.graph.run("MATCH (n) DETACH DELETE n")
        print("已清空数据库中的所有数据")

    def parse_json_file(self, file_path):
        """解析JSON文件并导入到Neo4j"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                return self.parse_api_data(data)
        except Exception as e:
            print(f"解析文件 {file_path} 时出错: {e}")
            return 0

    def parse_api_data(self, data):
        """解析API数据并导入到Neo4j"""
        tx = self.graph.begin()
        count = 0

        for item in data:
            if 'api_list' not in item or not item['api_list']:
                print(f"跳过: {item.get('filename', '无文件名')} - api_list为空")
                continue

            for api in item['api_list']:
                try:
                    # 创建API请求节点
                    api_node = self._create_api_node(tx, api)

                    # 创建参数节点和关系
                    param_nodes = self._create_parameter_nodes(tx, api, api_node)

                    # 创建响应结果节点和关系
                    response_node = self._create_response_node(tx, api, api_node)

                    count += 1
                except Exception as e:
                    print(f"处理API数据时出错: {e}")

        self.graph.commit(tx)
        return count

    def _create_api_node(self, tx, api):
        """创建API请求节点"""
        # 从URL中提取路径作为名称
        url = api['url']
        path = urlparse(url).path
        name = path

        # 创建节点
        api_node = Node(
            "APIRequest",
            name=name,
            method=api.get('method'),
            request_content_type=api.get('request_content_type')
        )
        tx.merge(api_node, "APIRequest", "name")
        return api_node

    def _create_parameter_nodes(self, tx, api, api_node):
        """创建参数节点及与API节点的关系"""
        post_data = api.get('post_data', '')
        params = {}

        # 处理GET请求的参数（从URL查询字符串中提取）
        if api.get('method') == 'GET':
            query = urlparse(api['url']).query
            if query:
                params = parse_qs(query)
                # 将参数值列表转为单个值（取第一个）
                params = {k: v[0] for k, v in params.items()}

        # 处理POST请求的参数
        elif post_data:
            # 处理form-urlencoded格式
            if isinstance(post_data, str) and '=' in post_data:
                for pair in post_data.split('&'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        # URL解码参数名
                        decoded_key = unquote(key)
                        params[decoded_key] = value
            # 可以在这里添加其他格式的处理逻辑（如JSON、XML）

        param_nodes = []

        # 创建参数节点和关系
        for param_name, param_value in params.items():
            param_node = Node(
                "Parameter",
                name=param_name,  # 直接使用原始参数名（包含[]）
                history_value=param_value,
                api_name=f'{api.get("method")}-{api_node["name"]}',  # 记录所属API
                desp=None
            )
            # tx.merge(param_node, "Parameter", "name")
            tx.create(param_node)  # 直接创建新节点，不进行合并

            # 创建关系
            rel = Relationship(api_node, "HAS_PARAMETER", param_node)
            tx.create(rel)

            param_nodes.append(param_node)

        return param_nodes

    def _create_response_node(self, tx, api, api_node):
        """创建响应结果节点及与API节点的关系"""
        # 从URL中提取路径作为基础名称
        url = api['url']
        path = urlparse(url).path
        method = api['method']

        # 创建响应节点
        response_node = Node(
            "APIResponse",
            name=f"{method}-{path}-响应结果",
            desp=None
        )
        tx.merge(response_node, "APIResponse", "name")

        # 创建关系
        rel = Relationship(api_node, "RETURNS", response_node)
        tx.create(rel)

        return response_node

    def update_single_api_description(self, api_description_data):
        """使用py2neo对象模型更新单个API的描述信息"""
        tx = self.graph.begin()

        try:
            # 解析API信息
            api_parts = api_description_data["api"].split(" ", 1)
            method = api_parts[0].strip()
            path = api_parts[1].split(" -- ")[0].strip()
            api_description = api_parts[1].split(" -- ")[1].strip()

            # 查询API节点
            api_matcher = NodeMatcher(self.graph)
            api_node = api_matcher.match("APIRequest", name=path, method=method).first()

            if not api_node:
                print(f"未找到API节点: {method} {path}")
                return False

            # 更新API描述
            api_node["desc"] = api_description
            tx.push(api_node)

            # 更新参数描述
            for param_desc in api_description_data["parameters"]:
                param_name = param_desc["name"]

                # 查询参数节点（使用api_name属性）
                param_matcher = NodeMatcher(self.graph)
                param_nodes = param_matcher.match(
                    "Parameter",
                    name=param_name,
                    api_name=f"{method}-{path}"  # 使用method+api_name属性匹配
                )

                if param_nodes.first():
                    param_node = param_nodes.first()

                    # 更新参数属性
                    param_node["desc"] = param_desc["description"]
                    param_node["required"] = param_desc["required"]
                    param_node["type"] = param_desc["type"]

                    tx.push(param_node)
                else:
                    print(f"未找到参数节点: {param_name}")

            # 更新响应描述
            response_matcher = NodeMatcher(self.graph)
            response_node = response_matcher.match("APIResponse", name=f"{method}-{path}-响应结果").first()

            if not response_node:
                print(f"未找到响应节点: {method} {path}")
                return False

            # 更新API描述
            response_node["desc"] = api_description_data["response"]
            tx.push(response_node)

            # 提交事务
            self.graph.commit(tx)
            print(f"成功更新API描述: {method} {path}")
            return True

        except Exception as e:
            print(f"更新API描述时出错: {e}")
            self.graph.rollback(tx)
            return False

    def update_param_analysis(self, parsed_data, current_api_name, current_api_method):
        tx = self.graph.begin()
        try:
            # 查找前置响应节点和当前API节点
            api_matcher = NodeMatcher(self.graph)

            current_node = api_matcher.match(
                "APIRequest", name=current_api_name, method=current_api_method
            ).first()

            # 处理参数分析
            self._update_parameters(tx, parsed_data["parameter_analysis"], current_node)

            self.graph.commit(tx)
            return True

        except Exception as e:
            print(f"更新数据库时出错: {e}")
            self.graph.rollback(tx)
            return False

    def _update_parameters(self, tx, parameter_info_list, api_node):
        """更新参数节点的属性"""

        # 查找前置响应节点和当前API节点
        matcher = NodeMatcher(self.graph)

        for param_info in parameter_info_list:
            param_name = param_info.get("name")
            if not param_name:
                continue

            param_node = matcher.match(
                "Parameter", name=param_name, api_name=f'{api_node.get("method")}-{api_node.get("name")}'
            ).first()

            if param_node:
                # 更新参数属性
                param_node["source"] = param_info.get("source", "unknown")
                param_node["conversion"] = param_info.get("conversion", "none")
                param_node["constraints"] = param_info.get("constraints", [])
                tx.push(param_node)
                print(f"已更新参数: {param_name}")

                # 处理前置API映射关系
                conversion = param_node["conversion"]
                if conversion.startswith("prefix API mapping ("):
                    # 提取前置API路径和方法
                    try:
                        api_info = conversion.split("(")[1].split(")")[0].strip()
                        method, path = api_info.split(" ", 1)

                        # 查找前置API节点
                        prefix_api_response_node = matcher.match(
                            "APIResponse", name=f"{method}-{path}-响应结果"
                        ).first()

                        if prefix_api_response_node:
                            # 创建关系 (Parameter)-[:MAPPED_FROM]->(API)
                            rel = Relationship(param_node, "MAPPED_FROM", prefix_api_response_node)
                            # 将关系添加到事务并提交
                            tx.create(rel)
                            print(f"已创建关系: {param_name} -> {method} {path}")
                        else:
                            print(f"警告：未找到前置API节点: {method} {path}")
                    except Exception as e:
                        print(f"错误：解析前置API信息失败: {conversion}, 错误: {e}")

            else:
                print(f"警告：未找到参数节点:{api_node.get('method')}  {api_node.get('name')}  {param_name}")

    def get_api_param_description(self, processed_data):
        """根据URL和method查找API节点及参数"""
        matcher = NodeMatcher(self.graph)
        rel_matcher = RelationshipMatcher(self.graph)
        results = []

        for item in processed_data:
            url = item['api']['url']
            method = item['api']['method']

            # 从URL提取路径作为节点名称
            path = urlparse(url).path

            # 查找API节点
            api_node = matcher.match("APIRequest",
                                     name=path,
                                     method=method).first()

            if api_node:
                # 使用关系匹配器查找关联的参数节点
                rels = rel_matcher.match((api_node,), r_type="HAS_PARAMETER")

                # 提取参数节点
                parameters = []
                for rel in rels:
                    param_node = rel.end_node
                    parameters.append({
                        'name': param_node['name'],
                        'history_value': param_node['history_value'],
                        'desc': param_node['desc']
                    })

                # 拼接API描述文本
                api_desc = api_node.get('desc', '')
                api_text = f" api info:{method}-{url}，api description:{api_desc}"

                # 拼接参数描述文本
                param_texts = []
                for param in parameters:
                    param_text = f" parameter '{param['name']}' description:{param['desc']},history value:{param['history_value']}"
                    param_texts.append(param_text)

                # 合并API和参数文本
                full_text = "\n".join([api_text] + param_texts)

                results.append(full_text)
            else:
                results.append("")

        return results

    def update_api_dependency(self, dependency_data):
        """根据API依赖数据构建图数据库"""
        for dependency in dependency_data['api_dependency']:
            # 解析依赖关系
            dependency_parts = dependency.split(" -> ")
            if len(dependency_parts) != 2:
                print(f"无效的依赖关系格式: {dependency}")
                continue

            source_api, target_api = dependency_parts
            source_method, source_path = self._parse_api_url(source_api)
            target_method, target_path = self._parse_api_url(target_api)

            matcher = NodeMatcher(self.graph)
            # 创建或获取API节点
            source_node = matcher.match("APIRequest", method=source_method, name=source_path).first()
            target_node = matcher.match("APIRequest", method=target_method, name=target_path).first()

            # 创建依赖关系
            if source_node and target_node:
                relationship = Relationship(source_node, "DEPENDS_ON", target_node)
                self.graph.create(relationship)
                print(f"创建关系: {source_api} -> {target_api}")

    def _parse_api_url(self, api_url):
        """使用urlparse从API URL中提取method和path"""
        try:
            # 分割方法和URL部分
            method_part, url_part = api_url.split(" ", 1)
            method = method_part.strip()

            # 解析URL获取路径
            parsed_url = urlparse(url_part)
            path = parsed_url.path
            return method, path
        except Exception as e:
            print(f"解析API URL失败: {api_url}, 错误: {e}")
            return None, None

    def get_api_plan(self):
        graph = self.graph
        api_query = """
        MATCH (req:APIRequest)
        // 匹配APIRequest之间的依赖关系
        OPTIONAL MATCH (otherReq:APIRequest)-[dep:DEPENDS_ON]->(req)
        // 匹配APIRequest到APIResponse的返回关系
        OPTIONAL MATCH (req)-[ret:RETURNS]->(res:APIResponse)
     
        RETURN 
            // APIRequest基本信息
            req.name AS api_path,
            req.method AS api_method,
            req.desc AS api_description,
            
            //  被哪些API依赖（反向依赖关系）
            CASE WHEN COUNT(otherReq) = 0 
                 THEN [] 
                 ELSE COLLECT(DISTINCT {
                     api_path: COALESCE(otherReq.name, null),
                     api_method: COALESCE(otherReq.method, null),
                     description: COALESCE(otherReq.desc, null)
                 }) 
            END AS preceding_requests,
            
            // APIRequest到APIResponse的返回关系
            COLLECT(DISTINCT {
                name: res.name,
                desc: res.desc
            }) AS response
        
        """

        results = graph.run(api_query).data()
        return results

    def get_filter_api_plan(self, selected_apis):
        """
        获取API计划数据，支持筛选特定API
        """
        graph = self.graph

        # 解析API列表为参数格式

        parsed_apis = [self.parse_api_string(api) for api in selected_apis]

        api_query = """
            UNWIND $apis AS api
            MATCH (req:APIRequest)
            WHERE req.name = api.name AND req.method = api.method
            // 匹配APIRequest之间的依赖关系
            OPTIONAL MATCH (otherReq:APIRequest)-[dep:DEPENDS_ON]->(req)
            // 匹配APIRequest到APIResponse的返回关系
            OPTIONAL MATCH (req)-[ret:RETURNS]->(res:APIResponse)

            RETURN 
                // APIRequest基本信息
                req.name AS api_path,
                req.method AS api_method,
                req.desc AS api_description,

                // 被哪些API依赖（反向依赖关系）
                CASE WHEN COUNT(otherReq) = 0 
                     THEN [] 
                     ELSE COLLECT(DISTINCT {
                         api_path: COALESCE(otherReq.name, null),
                         api_method: COALESCE(otherReq.method, null),
                         description: COALESCE(otherReq.desc, null)
                     }) 
                END AS preceding_requests,

                // APIRequest到APIResponse的返回关系
                COLLECT(DISTINCT {
                    name: res.name,
                    desc: res.desc
                }) AS response
            """

        results = graph.run(api_query, apis=parsed_apis).data()
        return results

    def get_api_parameters(self, method, url):
        # 构建Cypher查询
        query = """
        MATCH (api:APIRequest)-[:HAS_PARAMETER]->(param:Parameter)
        WHERE api.method = $method AND api.name = $url
        RETURN param.name AS name,
               param.type AS type,
               param.required AS required,
               param.desc AS description,
               param.constraints AS constraints,
               param.source AS source,
               param.history_value AS history_value,
               param.conversion AS conversion
        """

        # 执行查询
        result = self.graph.run(query, method=method, url=url)

        # 转换结果为字典列表
        parameters = []
        for record in result:
            parameters.append({
                "name": record["name"],
                "type": record["type"],
                "required": record["required"],
                "description": record["description"],
                "constraints": record["constraints"],
                "source": record["source"],
                "history_value": record["history_value"],
                "conversion": record["conversion"]
            })

        return parameters

    def get_mapped_parameters(self, method, url):
        """
        根据method和url查询具有MAPPED_FROM关系的参数节点及其对应的响应节点信息

        [{'param_name': 'menuIds', 'response_name': 'GET-/system/menu/roleMenuTreeData-响应结果', 'response_description': 'JSON array represents a hierarchical structure of role menu data (used to populate the menu tree in the UI).'}]
        """
        query = """
        MATCH (api:APIRequest)-[:HAS_PARAMETER]->(param:Parameter)-[:MAPPED_FROM]->(response:APIResponse)
        WHERE api.method = $method AND api.name = $url
        RETURN 
            param.name AS param_name,
            response.name AS response_name,
            response.desc AS response_description
        """

        result = self.graph.run(query, method=method, url=url)
        # 转换结果为字典列表
        parameters = []
        for record in result:
            parameters.append({
                "param_name": record["param_name"],
                "response_name": record["response_name"],
                "response_description": record["response_description"],
            })
        return parameters

    def get_content_type(self, method, url):
        matcher = NodeMatcher(self.graph)

        api_node = matcher.match("APIRequest",
                                 name=url,
                                 method=method).first()
        return api_node.get('request_content_type', '')

    def get_api_response_description(self, method, url):
        api_description, response_description = "", ""
        matcher = NodeMatcher(self.graph)
        api_request = matcher.match(
            "APIRequest",
            method=method,
            name=url
        ).first()

        # 如果找到APIRequest节点，获取其描述
        if api_request:
            api_description = api_request.get("desc")
            response_name = f"{method}-{url}-响应结果"
            api_response = matcher.match(
                "APIResponse",
                name=response_name
            ).first()

            if api_response:
                response_description = api_response.get("desc")

        return api_description, response_description

    def get_all_api_nodes(self):
        query = """
        MATCH (n:APIRequest)
        RETURN n.method AS method, n.name AS name, n.desc AS desc
        """
        results = self.graph.run(query)

        # 提取结果并转换为大模型需要的格式
        api_nodes = [
            {
                "api": f"{record['method']} {record['name']}",
                "api_description": record["desc"]
            }
            for record in results
        ]

        return api_nodes

    def get_dependency_closure(self, api_strings):
        """通过目标API节点查询依赖它的所有API节点"""
        # 解析输入的API字符串
        apis = [self.parse_api_string(s) for s in api_strings]

        # 执行反向查询
        query = """
    UNWIND $apis AS api
    // 查找所有下游节点（被依赖的节点）
    MATCH (downstream)-[:DEPENDS_ON*0..]->(:APIRequest {name: api.name, method: api.method})
    // 查找所有上游节点（依赖该节点的节点）
    MATCH (upstream)-[:DEPENDS_ON*0..]->(downstream)
    RETURN DISTINCT upstream.name AS name, upstream.method AS method
    """

        results = self.graph.run(query, apis=apis)

        complete_apis = [f"[{record['method']}] [{record['name']}]" for record in results]

        for api in api_strings:
            if api not in complete_apis:
                complete_apis.append(api)

        # 格式化结果
        return complete_apis

    def parse_api_string(self, api_string):
        """解析API字符串为method和name"""
        method_part, name_part = api_string.strip().split('] [', 1)
        method = method_part.replace('[', '').strip()
        name = name_part.replace(']', '').strip()
        return {"method": method, "name": name}


# 使用示例
if __name__ == "__main__":
    print(py2neo.__version__)

    file_path = r"E:\agent\Fairy\Fairy\api_files\output.json"
    parser = APIDataParser("bolt://localhost:7687", "neo4j", "12345678", "ruoyi")
    method = "POST"
    url = "/system/role/add"
    # all_api = parser.get_all_api_nodes()
    # print(all_api)
    #
    # all_api = ['[POST] [/system/role/checkRoleKeyUnique]','[POST] [/system/role/add]','[GET] [/system/test]']
    # all_related_apis = parser.get_dependency_closure(all_api)


    # mapped_params = parser.get_mapped_parameters(method, url)
    #
    # print(mapped_params)
    # content_type = parser.get_content_type(method, url)
    # print(content_type)


