import json

from neo4j import GraphDatabase
from urllib.parse import urlparse, parse_qs, unquote


class APIDataParser:
    def __init__(self, file_path, uri, user, password, database="neo4j", clear_existing=False):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.default_database = database
        self.file_path = file_path
        if clear_existing:
            self.clear_database()

    def clear_database(self):
        with self.driver.session(database=self.default_database) as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("已清空数据库中的所有数据")

    def parse_json_file(self):
        """解析JSON文件并导入到Neo4j"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                return self.parse_api_data(data)
        except Exception as e:
            print(f"解析文件 {self.file_path} 时出错: {e}")
            return 0

    def parse_api_data(self, data):
        """解析API数据并导入到Neo4j（官方Neo4j驱动版本）"""
        count = 0
        # 创建会话并开启事务（官方驱动通过session管理事务）
        with self.driver.session(database=self.default_database) as session:
            tx = session.begin_transaction()  # 显式开启事务
            try:
                for item in data:
                    if 'api_list' not in item or not item['api_list']:
                        print(f"跳过: {item.get('filename', '无文件名')} - api_list为空")
                        continue

                    for api in item['api_list']:
                        try:
                            # 1. 创建API请求节点（返回官方驱动的节点对象）
                            api_node = self._create_api_node(tx, api)
                            # 获取API节点的ID（用于后续关系创建）
                            api_node_id = api_node.element_id  # Neo4j 4.4+推荐用element_id，旧版本可用id(api_node)

                            # 2. 创建参数节点和关系（传入API节点ID）
                            param_nodes = self._create_parameter_nodes(tx, api, api_node_id)
                            #
                            # # 3. 创建响应结果节点和关系（传入API节点ID）
                            response_node = self._create_response_node(tx, api, api_node_id)

                            count += 1
                        except Exception as e:
                            print(f"处理API数据时出错: {e}")

                tx.commit()  # 所有操作完成后提交事务
            except Exception as e:
                tx.rollback()  # 出错时回滚
                print(f"事务提交失败，已回滚: {e}")
            finally:
                tx.close()  # 关闭事务

        return count

    def _create_api_node(self, tx, api):
        """创建API请求节点（官方Neo4j驱动版本）"""
        url = api['url']
        path = urlparse(url).path
        name = path

        # 创建/合并API节点（用MERGE确保唯一性）
        result = tx.run("""
            MERGE (n:APIRequest {name: $name})
            ON CREATE SET n.method = $method, 
                          n.request_content_type = $request_content_type
            ON MATCH SET n.method = $method, 
                         n.request_content_type = $request_content_type
            RETURN n
        """,
                        name=name,
                        method=api.get('method'),
                        request_content_type=api.get('request_content_type'))

        return result.single()[0]  # 返回创建的节点

    def _create_parameter_nodes(self, tx, api, api_node_id):
        """创建参数节点及与API节点的关系（官方Neo4j驱动版本）"""
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
            content_type = api.get('request_content_type', '').lower()
            # 处理 JSON 格式
            if 'application/json' in content_type:
                try:
                    json_params = json.loads(post_data)
                    params = {k: v if v is not None else "" for k, v in json_params.items()}

                except json.JSONDecodeError:
                    print("JSON 解析失败，使用原始字符串")
                    params = {'post_data': post_data}

            # 处理 form-urlencoded 格式
            elif 'application/x-www-form-urlencoded' in content_type and isinstance(post_data,
                                                                                    str) and '=' in post_data:
                for pair in post_data.split('&'):
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        # URL 解码参数名
                        decoded_key = unquote(key)
                        params[decoded_key] = value

        param_nodes = []
        for param_name, param_value in params.items():
            # 构建参数节点的唯一标识（参数名 + 所属API路径）
            api_path = urlparse(api["url"]).path
            api_method = api.get("method", "")
            api_name = f"{api_method}-{api_path}"

            # 使用MERGE确保在同一API中参数名唯一，同时记录历史值# 若数组为null，初始化为数组# 新增值到数组
            result = tx.run("""
                MERGE (p:Parameter {name: $name, api_name: $api_name})
                ON CREATE SET p.history_values = [$history_value],
                              p.desp = $desp
                ON MATCH SET 
                    p.history_values = CASE 
                        WHEN p.history_values IS NULL THEN [$history_value]  
                        WHEN NOT $history_value IN p.history_values THEN p.history_values + $history_value  
                        ELSE p.history_values 
                    END
                RETURN p
            """,  # 已存在则不重复添加
                            name=param_name,
                            history_value=str(param_value),
                            api_name=api_name,
                            desp=None)

            param_node = result.single()[0]

            # 创建关系（保持不变）
            tx.run("""
                MATCH (a) WHERE elementId(a) = $api_node_id
                MATCH (p:Parameter {name: $param_name, api_name: $api_name})
                MERGE (a)-[r:HAS_PARAMETER]->(p)
            """,
                   api_node_id=api_node_id,
                   param_name=param_name,
                   api_name=api_name)

            param_nodes.append(param_node)

        return param_nodes

    def _create_response_node(self, tx, api, api_node_id):

        # 从URL中提取路径作为基础名称（同原逻辑）
        url = api['url']
        path = urlparse(url).path
        method = api['method']
        node_name = f"{method}-{path}-响应结果"  # 响应节点的唯一名称

        # 1. 修复MERGE时desp为null的错误：仅用name作为唯一标识，desp在创建/匹配后设置 // 仅用name匹配，避免desp=null导致失败
        # 创建时设置desp（允许null） # 匹配时更新desp
        response_node = tx.run("""
            MERGE (n:APIResponse {name: $name})  
            ON CREATE SET n.desp = $desp  
            ON MATCH SET n.desp = $desp  
            RETURN n
        """, name=node_name, desp=None).single()["n"]

        # 2. 用elementId()替代id()，解决弃用警告 // 替换id(a)为elementId(a)# 用 MERGE 替代 CREATE，避免重复关系
        tx.run("""
            MATCH (a) WHERE elementId(a) = $api_node_id  
            MATCH (r:APIResponse {name: $response_name})
            MERGE (a)-[rel:RETURNS]->(r)  
        """, api_node_id=api_node_id, response_name=node_name)

        return response_node

    def update_single_api_description(self, api_description_data):
        """使用py2neo对象模型更新单个API的描述信息"""
        with self.driver.session(database=self.default_database) as session:
            tx = session.begin_transaction()
            # try:
            # 解析API信息
            method = api_description_data["api_method"]
            path = api_description_data["api_path"]
            api_description = api_description_data["api_description"]
            api_template = api_description_data.get("api_template")  # 新增：获取api_template
            api_name = f"{method}-{path}"  # 构建API唯一标识（与原代码一致）

            api_node = None
            # 1. 查询并更新API节点
            template_match = tx.run("""
                MATCH (a:APIRequest {method: $method, api_template: $api_template})
                RETURN a
            """, method=method, api_template=api_template).single()
            if template_match:
                api_node = template_match["a"]

            # 2. 若未匹配到，处理「首次创建」或「历史节点未设置api_template」的情况
            if not api_node:
                # 2.1 尝试通过「method + path」匹配（可能是首次创建，或历史节点未设置api_template）
                path_match = tx.run("""
                    MATCH (a:APIRequest {method: $method, name: $path})
                    RETURN a
                """, method=method, path=path).single()

                if path_match:
                    # 找到第一次（未设置api_template）节点，更新其api_template
                    api_node = path_match["a"]
                    tx.run("""
                        MATCH (a:APIRequest {method: $method, name: $path})
                        SET a.api_template = $api_template
                    """, method=method, path=path, api_template=api_template)


            # 若仍未获取到API节点，说明创建失败
            if not api_node:
                print(f"API节点创建/匹配失败: {method} {path}")
                tx.rollback()
                return False

            # 更新API节点描述（替换tx.push()）
            tx.run("""
                MATCH (a:APIRequest {api_template: $api_template, method: $method})
                SET a.desc = $api_description
            """, method=method, api_description=api_description, api_template=api_template)

            # 更新参数描述
            for param_desc in api_description_data["parameters"]:
                param_name = param_desc["name"]
                param_dynamic_value = param_desc.get("dynamic_value", "")

                # 1. 优先通过「param_name + api_template」匹配（新逻辑，不受动态参数影响）
                param_node = None
                template_match = tx.run("""
                    MATCH (p:Parameter {name: $param_name, api_template: $api_template})
                    RETURN p
                """, param_name=param_name, api_template=api_template).single()
                if template_match:
                    param_node = template_match["p"]
                # 2. 若未匹配到，尝试用旧标识「param_name + api_name_old」匹配旧节点（无api_template的历史节点）
                if not param_node:
                    old_match = tx.run("""
                        MATCH (p:Parameter {name: $param_name, api_name: $api_name})
                        RETURN p
                    """, param_name=param_name, api_name=api_name).single()

                    if old_match:
                        # 找到旧节点，补充设置api_template完成升级
                        param_node = old_match["p"]
                        tx.run("""
                            MATCH (p:Parameter {name: $param_name, api_name: $api_name})
                            SET p.api_template = $api_template 
                        """, param_name=param_name, api_name=api_name, api_template=api_template)

                # 3. 若仍未匹配到,此时即为初次创建的动态参数，创建新参数节点（包含api_template属性）
                if not param_node:
                    print(f"创建新动态参数节点: {param_name} (模板: {api_template})")
                    # 初始化历史值（跳过空值）
                    initial_history = []
                    if param_dynamic_value != "":
                        # 新增类型转换逻辑
                        # try:
                        #     if param_dynamic_value.isdigit():
                        #         value = int(param_dynamic_value)
                        #     else:
                        #         value = param_dynamic_value
                        # except ValueError:
                        #     try:
                        #         value = float(param_dynamic_value)
                        #     except ValueError:
                        #         value = param_dynamic_value

                        value = str(param_dynamic_value)

                        initial_history = [value]
                    # 创建节点：同时保留旧api_name（兼容）和新api_template（核心标识）
                    tx.run("""
                        CREATE (p:Parameter {
                            name: $param_name,
                            api_name: $api_name, 
                            api_template: $api_template, 
                            desc: $desc,
                            required: $required,
                            location: $location,
                            history_values: $initial_history
                        })
                    """,
                           param_name=param_name,
                           api_name=api_name,
                           api_template=api_template,
                           desc=param_desc["description"],
                           required=param_desc.get("required", ""),
                           location=param_desc["location"],
                           initial_history=initial_history
                           )
                    # 建立与API节点的关系（HAS_PARAMETER）
                    tx.run("""
                        MATCH (a:APIRequest {method: $method, api_template: $api_template}),
                              (p:Parameter {name: $param_name, api_template: $api_template})    
                        CREATE (a)-[:HAS_PARAMETER]->(p)
                    """, method=method, api_template=api_template, param_name=param_name)# 可能存在问题，即method不同的api，这里api做了method的区分，由于param与api存在关系
                    # 重新查询新创建的节点
                    param_node = tx.run("""
                        MATCH (p:Parameter {name: $param_name, api_template: $api_template})
                        RETURN p
                    """, param_name=param_name, api_template=api_template).single()["p"]
                # 4. 无论节点是匹配到的（新/旧），更新其属性（尤其是history_values）
                current_history = param_node.get("history_values", [])  # 获取现有历史值
                # 仅追加非空且未重复的动态值
                if param_dynamic_value != "":
                    # 新增类型转换
                    # try:
                    #     if param_dynamic_value.isdigit():
                    #         value = int(param_dynamic_value)
                    #     else:
                    #         value = param_dynamic_value
                    # except ValueError:
                    #     try:
                    #         value = float(param_dynamic_value)
                    #     except ValueError:
                    #         value = param_dynamic_value

                    value = str(param_dynamic_value)

                    if value not in current_history:
                        updated_history = current_history + [value]
                    else:
                        updated_history = current_history
                else:
                    updated_history = current_history

                # 更新参数节点属性（替换tx.push()）
                tx.run("""
                    MATCH (p:Parameter {name: $param_name, api_template: $api_template})
                    SET p.desc = $desc,
                        p.required = $required,
                        p.location = $location,
                        p.history_values = $updated_history;
                """,
                       param_name=param_name,
                       api_template=api_template,
                       desc=param_desc["description"],
                       required=param_desc["required"],
                       location=param_desc.get("location", ""),
                       updated_history=updated_history
                       )

            # 3. 更新响应描述
            response_name = f"{method}-{path}-响应结果"
            response_template_name = f"{method}-{api_template}-响应结果"
            # 1. 优先通过「method + api_template + 后缀」匹配（新逻辑）
            response_node = None
            template_response = tx.run("""
                MATCH (r:APIResponse {template_name: $response_template_name})
                RETURN r
            """, response_template_name=response_template_name).single()
            if template_response:
                response_node = template_response["r"]
            # 2. 若未匹配到，尝试通过「method + 完整path + 后缀」匹配旧节点
            if not response_node:
                path_response = tx.run("""
                    MATCH (r:APIResponse {name: $response_name})
                    RETURN r
                """, response_name=response_name).single()
                if path_response:
                    response_node = path_response["r"]
                    # 若旧节点存在，补充设置api_template（升级为新逻辑）
                    if api_template:
                        tx.run("""
                            MATCH (r:APIResponse {name: $response_name})
                            SET r.api_template = $api_template,
                                r.template_name = $response_template_name  
                        """, response_name=response_name, api_template=api_template,
                               response_template_name=response_template_name)

            # 更新响应节点描述（替换tx.push()）
            tx.run("""
                MATCH (r:APIResponse {template_name: $response_template_name})
                SET r.desc = $response_desc
            """,  response_template_name=response_template_name, response_desc=api_description_data["response_description"])

            # 提交事务（替换self.graph.commit()）
            tx.commit()
            print(f"成功更新API描述: {method} {path}")
            return True

    def update_param_analysis(self, parsed_data, current_api_name, current_api_method):
        with self.driver.session(database=self.default_database) as session:
            tx = session.begin_transaction()
            try:
                # 1. 查找当前API节点（替换NodeMatcher）
                # 匹配条件：标签为APIRequest，name=current_api_name，method=current_api_method
                current_node = tx.run("""
                    MATCH (a:APIRequest {name: $api_name, method: $api_method})
                    RETURN elementId(a) AS id, a.name AS name, a.method AS method
                """, api_name=current_api_name, api_method=current_api_method).single()

                if not current_node:
                    print(f"未找到API节点: {current_api_method} {current_api_name}")
                    tx.rollback()
                    return False

                # 2. 调用参数更新方法（假设_update_parameters已适配官方驱动）
                # 注意：若_update_parameters仍使用py2neo语法，需同步更新为官方驱动方式
                self._update_parameters(tx, parsed_data["parameter_analysis"], current_node["id"])

                # 3. 提交事务
                tx.commit()
                return True

            except Exception as e:
                print(f"更新数据库时出错: {e}")
                tx.rollback()
                return False

    def _update_parameters(self, tx, parameter_info_list, api_node_id):
        """更新参数节点的属性"""

        # 1. 获取当前API节点的信息（method和name）
        api_info = tx.run("""
            MATCH (a) WHERE elementId(a) = $api_node_id
            RETURN a.method AS method, a.name AS name
        """, api_node_id=api_node_id).single()

        if not api_info:
            print(f"错误：无法获取API节点信息，ID={api_node_id}")
            return

        api_method = api_info["method"]
        api_name = api_info["name"]
        current_api_name = f"{api_method}-{api_name}"  # 构建api_name

        for param_info in parameter_info_list:
            param_name = param_info.get("name")
            if not param_name:
                continue

            # 2. 查询参数节点
            param_node = tx.run("""
                MATCH (p:Parameter {name: $param_name, api_name: $api_name})
                RETURN p
            """, param_name=param_name, api_name=current_api_name).single()

            if param_node:
                param_node = param_node["p"]  # 获取节点对象

                # 3. 更新参数属性
                tx.run("""
                    MATCH (p:Parameter {name: $param_name, api_name: $api_name})
                    SET p.source = $source,
                        p.conversion = $conversion,
                        p.constraints = $constraints
                """,
                       param_name=param_name,
                       api_name=current_api_name,
                       source=param_info.get("source", "unknown"),
                       conversion=param_info.get("conversion", "none"),
                       constraints=param_info.get("constraints", []))

                print(f"已更新参数: {param_name}")

                # 处理前置API映射关系
                conversion = param_info.get("conversion", "none")
                if conversion.startswith("prefix API mapping ("):
                    # 提取前置API路径和方法
                    try:
                        # 提取前置API信息
                        api_info_str = conversion.split("(")[1].split(")")[0].strip()
                        prefix_method, prefix_path = api_info_str.split(" ", 1)
                        prefix_response_name = f"{prefix_method}-{prefix_path}-响应结果"

                        # 查询前置API响应节点
                        prefix_node = tx.run("""
                            MATCH (r:APIResponse {name: $response_name})
                            RETURN r
                        """, response_name=prefix_response_name).single()

                        if prefix_node:
                            # 创建映射关系
                            tx.run("""
                                MATCH (p:Parameter {name: $param_name, api_name: $api_name})
                                MATCH (r:APIResponse {name: $response_name})
                                MERGE (p)-[rel:MAPPED_FROM]->(r)
                            """,
                                   param_name=param_name,
                                   api_name=current_api_name,
                                   response_name=prefix_response_name)

                            print(f"已创建关系: {param_name} -> {prefix_method} {prefix_path}")
                        else:
                            print(f"警告：未找到前置API节点: {prefix_method} {prefix_path}")
                    except Exception as e:
                        print(f"错误：解析前置API信息失败: {conversion}, 错误: {e}")

            else:
                print(f"警告：未找到参数节点: {api_method} {api_name} {param_name}")

    def get_api_param_description(self, processed_data):
        """根据URL和method查找API节点及参数"""
        results = []
        with self.driver.session(database=self.default_database) as session:
            for item in processed_data:
                url = item['api']['url']
                method = item['api']['method']
                path = urlparse(url).path

                # 1. 查询API节点（替换NodeMatcher）
                api_node = session.run("""
                    MATCH (a:APIRequest {name: $path, method: $method})
                    RETURN a.desc AS desc
                """, path=path, method=method).single()

                if api_node:
                    api_desc = api_node["desc"] if api_node["desc"] else ""
                    api_text = f" api info:{method}-{path}，api description:{api_desc}"

                    # 2. 查询关联的参数节点（替换RelationshipMatcher）
                    params = session.run("""
                        MATCH (a:APIRequest {name: $path, method: $method})-[:HAS_PARAMETER]->(p:Parameter)
                        RETURN p.name AS name, p.history_values AS history_values, p.desc AS desc
                    """, path=path, method=method).data()

                    # 3. 拼接参数描述文本
                    param_texts = []
                    for param in params:
                        param_text = f" parameter '{param['name']}' description:{param['desc']},history values:{param['history_values']}"
                        param_texts.append(param_text)

                    # 4. 合并API和参数文本
                    full_text = "\n".join([api_text] + param_texts)
                    results.append(full_text)
                else:
                    results.append("")

        return results

    def get_analyzed_api_param(self, item):
        """根据URL和method查找API节点及参数的constraints属性"""
        url = item['api']['url']
        method = item['api']['method']
        path = urlparse(url).path

        with self.driver.session(database=self.default_database) as session:
            # 1. 查询API节点
            api_node = session.run("""
                MATCH (a:APIRequest {name: $path, method: $method})
                RETURN a
            """, path=path, method=method).single()

            if api_node:
                # 2. 查询关联的参数节点及其constraints属性
                params = session.run("""
                    MATCH (a:APIRequest {name: $path, method: $method})-[:HAS_PARAMETER]->(p:Parameter)
                    RETURN 
                        p.name AS name, 
                        p.location AS location,
                        p.api_template AS api_template,
                        p.history_values AS history_values,
                        p.desc AS desc,
                        COALESCE(p.source, null) AS source, 
                        COALESCE(p.conversion, null) AS conversion,
                        COALESCE(p.constraints, null) AS constraints
                """, path=path, method=method).data()

                # 3. 构建结果列表（参数名 -> constraints）
                return [
                    {
                        "name": param["name"],
                        "desc": param["desc"],
                        "location": param["location"],
                        "api_template": param["api_template"],
                        "history_values": param["history_values"],
                        "source": param["source"],
                        "conversion": param["conversion"],
                        "constraints": param["constraints"]
                    }
                    for param in params
                ]
            else:
                return None

    def update_api_dependency(self, dependency_data):
        """根据API依赖数据构建图数据库"""
        with self.driver.session(database=self.default_database) as session:
            for dependency in dependency_data['api_dependency']:
                # 解析依赖关系
                dependency_parts = dependency.split(" → ")
                if len(dependency_parts) != 2:
                    print(f"无效的依赖关系格式: {dependency}")
                    continue

                source_api, target_api = dependency_parts
                source_method, source_path = self._parse_api_url(source_api)
                target_method, target_path = self._parse_api_url(target_api)

                try:
                    # 1. 查找源API节点和目标API节点
                    # 使用MERGE确保节点存在（如果不存在可创建空节点，或仅匹配已存在节点）
                    # 这里选择仅匹配已存在节点（若不存在则不创建关系）
                    result = session.run("""
                        MATCH (source:APIRequest {method: $source_method, name: $source_path})
                        MATCH (target:APIRequest {method: $target_method, name: $target_path})
                        RETURN source, target
                    """,
                                         source_method=source_method,
                                         source_path=source_path,
                                         target_method=target_method,
                                         target_path=target_path).single()

                    if not result:
                        print(f"源API或目标API节点不存在: {source_api} -> {target_api}")
                        continue

                    # 2. 创建/合并依赖关系（用MERGE避免重复创建）# 确保关系唯一
                    session.run("""
                        MATCH (source:APIRequest {method: $source_method, name: $source_path})
                        MATCH (target:APIRequest {method: $target_method, name: $target_path})
                        MERGE (source)-[rel:DEPENDS_ON]->(target)  
                    """,
                                source_method=source_method,
                                source_path=source_path,
                                target_method=target_method,
                                target_path=target_path)

                    print(f"创建/确认关系: {source_api} -> {target_api}")

                except Exception as e:
                    print(f"处理依赖关系时出错: {e}")

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
        with self.driver.session(database=self.default_database) as session:
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
            # 执行查询并获取结果
            results = session.run(api_query).data()
        return results

    def get_filter_api_plan(self, selected_apis):
        """
        获取API计划数据，支持筛选特定API
        """
        parsed_apis = [self.parse_api_string(api) for api in selected_apis]
        with self.driver.session(database=self.default_database) as session:
            api_query = """
                UNWIND $apis AS api
                MATCH (req:APIRequest)
                WHERE req.api_template = api.api_template AND req.method = api.method
                // 匹配APIRequest之间的依赖关系
                OPTIONAL MATCH (otherReq:APIRequest)-[dep:DEPENDS_ON]->(req)
                // 匹配APIRequest到APIResponse的返回关系
                OPTIONAL MATCH (req)-[ret:RETURNS]->(res:APIResponse)
    
                RETURN 
                    // APIRequest基本信息
                    req.name AS api_path,
                    req.api_template AS api_template,
                    req.method AS api_method,
                    req.desc AS api_description,
    
                    // 被哪些API依赖（反向依赖关系）
                    CASE WHEN COUNT(otherReq) = 0 
                         THEN [] 
                         ELSE COLLECT(DISTINCT {
                             api_path: COALESCE(otherReq.name, null),
                             api_template: COALESCE(otherReq.api_template, null),
                             api_method: COALESCE(otherReq.method, null),
                             description: COALESCE(otherReq.desc, null)
                         }) 
                    END AS preceding_requests,
    
                    // APIRequest到APIResponse的返回关系
                    COLLECT(DISTINCT {
                        name: res.name,
                        api_template: res.api_template,
                        desc: res.desc
                    }) AS response
                """
            # 执行查询并返回结果（参数传递方式与原逻辑一致）
            results = session.run(
                api_query,
                apis=parsed_apis  # 传递解析后的API列表给Cypher的$apis参数
            ).data()

        return results

    def get_api_parameters(self, method, api_template):
        # 构建Cypher查询
        query = """
        MATCH (api:APIRequest)-[:HAS_PARAMETER]->(param:Parameter)
        WHERE api.method = $method AND api.api_template = $api_template
        RETURN param.name AS name,
               param.api_template AS api_template,
               param.location AS location,
               param.type AS type,
               param.required AS required,
               param.desc AS description,
               param.constraints AS constraints,
               param.source AS source,
               param.history_value AS history_value,
               param.conversion AS conversion
        """

        # 使用官方驱动会话执行查询
        with self.driver.session(database=self.default_database) as session:
            # 执行查询（参数传递方式与原逻辑一致）
            result = session.run(query, method=method, api_template=api_template)

            # 转换结果为字典列表（官方驱动的data()方法直接返回字典列表）
            parameters = result.data()

        return parameters

    def get_mapped_parameters(self, method, api_template):
        """
        根据method和url查询具有MAPPED_FROM关系的参数节点及其对应的响应节点信息
        [{'param_name': 'menuIds', 'response_name': 'GET-/system/menu/roleMenuTreeData-响应结果', 'response_description': 'JSON array represents a hierarchical structure of role menu data (used to populate the menu tree in the UI).'}]
        """
        query = """
        MATCH (api:APIRequest)-[:HAS_PARAMETER]->(param:Parameter)-[:MAPPED_FROM]->(response:APIResponse)
        WHERE api.method = $method AND api.api_template = $api_template
        RETURN 
            param.name AS param_name,
            response.api_template AS api_template,
            response.name AS response_name,
            response.desc AS response_description
        """

        # 使用官方驱动会话执行查询
        with self.driver.session(database=self.default_database) as session:
            result = session.run(query, method=method, api_template=api_template)

            # 转换结果为字典列表（官方驱动的data()方法直接返回字典列表）
            parameters = result.data()
        return parameters

    def get_content_type(self, method, api_template):
        """根据method和url查询APIRequest节点的request_content_type属性"""
        # 构建Cypher查询，匹配API节点并返回request_content_type
        query = """
        MATCH (api:APIRequest {api_template: $api_template, method: $method})
        RETURN api.request_content_type AS content_type
        """

        # 使用官方驱动会话执行查询
        with self.driver.session(database=self.default_database) as session:
            result = session.run(query, api_template=api_template, method=method).single()

        # 处理结果：存在节点则返回属性值（默认空字符串），否则返回空字符串
        return result["content_type"] if (result and result["content_type"] is not None) else ""

    def get_api_response_description(self, method, api_template):
        api_description, response_description = "", ""

        # 1. 查询APIRequest节点的描述
        api_query = """
           MATCH (api:APIRequest {method: $method, api_template: $api_template})
           RETURN api.desc AS api_desc
           """

        with self.driver.session(database=self.default_database) as session:
            # 执行APIRequest查询
            api_result = session.run(api_query, method=method, api_template=api_template).single()

            if api_result:
                # 处理API描述（默认空字符串，避免None）
                api_description = api_result["api_desc"] or ""

                # 2. 构建响应节点名称并查询APIResponse节点
                response_query = """
                   MATCH (res:APIResponse {api_template: $api_template})
                   RETURN res.desc AS response_desc
                   """
                response_result = session.run(response_query, api_template=api_template).single()

                # 处理响应描述（默认空字符串）
                if response_result:
                    response_description = response_result["response_desc"] or ""

        return api_description, response_description

    def get_all_api_nodes(self):
        query = """
        MATCH (n:APIRequest)
        RETURN n.method AS method, n.name AS name, n.desc AS desc, n.api_template as api_template
        """
        # 使用官方驱动会话执行查询
        with self.driver.session(database=self.default_database) as session:
            results = session.run(query)

            # 提取结果并转换为大模型需要的格式
            api_nodes = [
                {
                    "api": f"{record['method']} {record['name']}",
                    "api_template": record['api_template'],
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

        with self.driver.session(database=self.default_database) as session:
            results = session.run(query, apis=apis)

            # 提取结果并格式化为"[METHOD] [PATH]"
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
        return {"method": method, "api_template": name}

    def test_update_single_api_description(self):
        test_data = {
            "api": "POST /system/user/profile/resetPwd -- 用户密码更新接口，用于验证旧密码并设置新密码",
            "parameters": [
                {
                    "name": "oldPassword",
                    "description": "用户当前使用的旧密码",
                    "required": True,
                    "type": "string"
                },
                {
                    "name": "newPassword",
                    "description": "用户待设置的新密码（需符合复杂度要求）",
                    "required": True,
                    "type": "string"
                }
            ],
            "response": "返回更新结果，成功时包含提示信息，失败时包含错误原因"
        }
        self.update_single_api_description(api_description_data=test_data)


    def test_up(self):
        data = {
          "api_method": "PUT",
          "api_path": "/api/v1/Account/123/starSubscription",
          "api_template": "/api/v1/Account/{AccountID}/starSubscription",
          "api_description": "This API is called when a user stars a subscription for a specific account. It updates the subscription status for the account identified by the AccountID.",
          "parameters": [
            {
              "name": "AccountID",
              "description": "The unique identifier of the account for which the subscription is being starred.",
              "location": "path",
              "required": True,
              "dynamic_value": "123"
            }
          ],
          "response_description": "Boolean response indicating whether the subscription was successfully starred. A value of 'true' means the operation was successful."
        }
        self.update_single_api_description(data)
    def test_update_param_analysis(self):
        api_name = "/system/user/checkPhoneUnique"
        api_method = "POST"

        parsed_data = {
            "parameter_analysis": [
                {
                    "name": "phonenumber",
                    "source": "user_input",
                    "conversion": "none",
                    "constraints": ["required", "min_length:3"]
                },
                {
                    "name": "userId",
                    "source": "user_input",
                    "conversion": "prefix API mapping (GET /system/user/profile/checkPassword)",
                    "constraints": ["required", "format:email"]
                }
            ]
        }
        self.update_param_analysis(parsed_data=parsed_data, current_api_name=api_name,
                                   current_api_method=api_method)

    def test_get_api_param_description(self):
        processed_data = [
            {
                "api": {
                    "url": "https://example.com/system/user/profile/resetPwd",  # 路径为 /api/users
                    "method": "POST"
                }
            }
        ]
        print(self.get_api_param_description(processed_data))

    def test_update_api_dependency(self):
        dependency_data = {'api_dependency': [
            'GET http://localhost:8088/system/menu/roleMenuTreeData -> POST http://localhost:8088/system/role/checkRoleNameUnique',
            'POST http://localhost:8088/system/role/checkRoleNameUnique -> POST http://localhost:8088/system/role/checkRoleKeyUnique',
            'POST http://localhost:8088/system/role/checkRoleKeyUnique -> POST http://localhost:8088/system/role/add']}

        self.update_api_dependency(dependency_data)

    def test_get_api_plan(self):
        print(self.get_api_plan())

    def test_get_filter_api_plan(self):
        l = ['[POST] [/system/role/checkRoleKeyUnique]', '[POST] [/system/role/add]',
             '[GET] [/system/menu/roleMenuTreeData]', '[GET] [/system/test]']

        plan = self.get_filter_api_plan(l)
        print(plan)

    def test_get_dependency_closure(self):
        all_api = ['[POST] [/system/role/checkRoleKeyUnique]', '[POST] [/system/role/add]', '[GET] [/system/test]']
        all_related_apis = self.get_dependency_closure(all_api)
        print(all_related_apis)

    def test_get_analyzed_api_param(self):
        item = {
            "api": {
                "url": "https://example.com/system/user/profile/checkPassword",
                "method": "GET"
            }
        }
        analyzed_param = self.get_analyzed_api_param(item)

        has_analyzed_params = analyzed_param and (
                analyzed_param[0]["source"] is not None or
                analyzed_param[0]["conversion"] is not None
        )

        print(has_analyzed_params)

        if analyzed_param:
            # 格式化历史参数分析结果，使其更易读
            param_text = "\n".join([
                f"- name: {param['name']}, description: {param['desc']} \n"
                f"-- history_values:{param['history_values']},  source={param['source']}, conversion={param['conversion']}, constraints={param['constraints']}"
                for param in analyzed_param
            ])
            prompt = f"Historical parameter analysis results: \n{param_text}\n"
            print(prompt)

# 使用示例
if __name__ == "__main__":
    from Fairy.config.config import *
    # parser = APIDataParser(r"E:\agent\api\jeecg-修改请假类型和请假事由\output.json", "bolt://localhost:7687", "neo4j", "12345678", "jeecg")

    parser = APIDataParser(APIDataParser_path, neo4j_url, neo4j_user, neo4j_password, nro4j_database, clear_existing=False)
    parser.parse_json_file()
    # parser.test_up()
    # parser.test_get_analyzed_api_param()
    # method = "POST"
    # url = "/system/role/add"
    # mapped_params = parser.get_mapped_parameters(method, url)
    # print(mapped_params)screenshot

    # content_type = parser.get_content_type(method, url)
    # print(content_type)
