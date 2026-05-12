#!/usr/bin/env python3
"""bug-book MCP Server：提供所有 bug 操作的 MCP tool"""

import json
import sys
import os
from pathlib import Path
from typing import Any, Optional

# 导入工厂和接口
from backend_factory import create_backend
from storage_backend import BugStorageBackend


# ---------------------------------------------------------------------------
# MCP Server 实现
# ---------------------------------------------------------------------------

class MCPServer:
    """bug-book MCP Server"""

    def __init__(self, storage_path=None):
        self.storage_path = storage_path
        # 通过工厂创建后端实例（依赖注入）
        self.backend: BugStorageBackend = create_backend()

    def handle_request(self, request: dict) -> dict:
        """处理 MCP 请求"""
        method = request.get('method')
        params = request.get('params', {})
        request_id = request.get('id')

        # MCP 初始化请求
        if method == 'initialize':
            return {
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'protocolVersion': '2024-11-05',
                    'capabilities': {
                        'tools': {},
                    },
                    'serverInfo': {
                        'name': 'bug-book',
                        'version': '1.0.0'
                    }
                }
            }
        elif method == 'tools/list':
            return {'jsonrpc': '2.0', 'id': request_id, 'result': self.list_tools()}
        elif method == 'tools/call':
            tool_name = params.get('name')
            arguments = params.get('arguments', {})
            return {'jsonrpc': '2.0', 'id': request_id, 'result': self.call_tool(tool_name, arguments)}
        elif method == 'ping':
            # MCP ping 用于检测连通性，必须返回空 result
            return {'jsonrpc': '2.0', 'id': request_id, 'result': {}}
        elif method == 'notifications/initialized':
            # 客户端初始化完成确认，notification 不需要响应
            return None
        else:
            return {'jsonrpc': '2.0', 'id': request_id, 'error': {'code': -32601, 'message': f'Unknown method: {method}'}}

    def list_tools(self) -> list:
        """返回所有可用工具"""
        return [
            # CRUD
            self._tool('add_bug', '新增一条 bug 记录',
                '新增一条 bug 记录到数据库。\n\n返回: {bug_id, score}\n\n使用场景：用户报告新问题时调用'),
            self._tool('update_bug', '更新 bug 记录',
                '更新 bug 的标题、现象、根因、解决方案等字段'),
            self._tool('delete_bug', '删除 bug',
                '将 bug 标记为无效（软删除）'),
            self._tool('mark_invalid', '标记 bug 失效',
                '标记 bug 为 invalid，可选提供失效原因'),
            self._tool('increment_score', '累加分数',
                '累加某维度的分数（difficulty/emotion/occurrences）'),

            # 查询
            self._tool('get_bug_detail', '获取 bug 详情',
                '获取 bug 的完整信息，包括 scores、paths、tags、recalls、impacts 等'),
            self._tool('list_bugs', '列出 bugs',
                '分页列出 bugs，支持按状态筛选、排序'),
            # count_bugs - skill 未使用
            # update_bug_paths - 被 migrate 替代
            # update_bug_recalls - 被 migrate 替代
            # add_recall - 被 migrate 替代

            # 搜索
            self._tool('search_by_keyword', '关键词搜索',
                '按关键词搜索 bug，支持标题、现象、关键词匹配'),
            self._tool('search_by_tag', '标签搜索',
                '按标签搜索 bug'),
            self._tool('search_recent', '搜索最近创建的',
                '搜索最近 N 天创建的 bugs'),
            self._tool('search_high_score', '搜索高分 bugs',
                '搜索分数超过阈值的 bugs'),
            self._tool('search_top_critical', '搜索最严重的',
                '搜索最严重的前 N 个 bugs（高分+未验证）'),
            self._tool('search_recent_unverified', '搜索最近未验证的',
                '搜索最近 N 天创建但未验证的 bugs'),
            self._tool('search_by_status_and_score', '组合搜索',
                '按状态、分数范围、验证状态组合搜索'),

            # 召回
            # self._tool('recall_by_path', '按路径召回',
            #     '根据文件路径召回相关 bug，用于改代码前检查'),
            # self._tool('recall_by_path_full', '按路径召回完整上下文',
            #     '召回相关 bug 及其影响关系（正向+反向）'),
            self._tool('recall_by_pattern', '按模式召回',
                '根据 autoRecall pattern 召回相关 bug'),
            self._tool('recall_by_path_for_hook', '按路径召回（Hook专用）',
                '为Hook返回additionalContext格式的召回结果，包含缓存机制'),

            # 影响关系
            # get_impacted_bugs - 被 recall_by_path_full 内部调用
            # get_bug_impacts - 被 get_bug_detail 替代
            self._tool('add_impact', '添加影响关系',
                '记录 bug 对某个路径的影响'),
            self._tool('analyze_impact_patterns', '分析影响模式',
                '分析高频回归的路径模式'),
            # update_impacted_paths - 被 migrate 替代
            # delete_impact - skill 未实现

            # 高级
            self._tool('list_unverified_old', '列出长期未验证的',
                '列出长期未验证的 bugs'),
            self._tool('check_path_valid', '检查路径有效性',
                '检查路径是否仍存在于代码库'),
            self._tool('check_bug_paths', '检查 bug 路径有效性',
                '检查 bug 的 paths/recalls/impacts 路径是否有效，返回无效路径列表'),
            # self._tool('migrate_bug_paths_after_refactor', '迁移重构后的路径',
            #     '重构后自动迁移相关 bug 的路径和 recalls'),
            self._tool('migrate_from_bash_command', '从Bash命令迁移路径',
                '接收mv/git mv命令，自动提取路径并迁移bug记录'),
        ]

    def _tool(self, name: str, description: str, long_description: str = '') -> dict:
        """构建 tool 定义"""
        return {
            'name': f'mcp__bug_book__{name}',
            'description': long_description or description,
            'inputSchema': self._get_input_schema(name),
        }

    def _get_input_schema(self, tool_name: str) -> dict:
        """获取 tool 的输入 schema"""
        schemas = {
            'add_bug': {
                'type': 'object',
                'properties': {
                    'title': {'type': 'string'},
                    'phenomenon': {'type': 'string'},
                    'root_cause': {'type': 'string'},
                    'solution': {'type': 'string'},
                    'test_case': {'type': 'string'},
                    'verified': {'type': 'boolean'},
                    'scores': {'type': 'object'},
                    'paths': {'type': 'array', 'items': {'type': 'string'}},
                    'tags': {'type': 'array', 'items': {'type': 'string'}},
                    'keywords': {'type': 'array', 'items': {'type': 'string'}},
                    'recalls': {'type': 'array', 'items': {'type': 'string'}},
                },
                'required': ['title', 'phenomenon'],
            },
            'update_bug': {
                'type': 'object',
                'properties': {
                    'bug_id': {'type': 'integer'},
                    'title': {'type': 'string'},
                    'phenomenon': {'type': 'string'},
                    'root_cause': {'type': 'string'},
                    'solution': {'type': 'string'},
                    'test_case': {'type': 'string'},
                    'status': {'type': 'string'},
                    'verified': {'type': 'boolean'},
                    'verified_at': {'type': 'string'},
                    'verified_by': {'type': 'string'},
                },
                'required': ['bug_id'],
            },
            'delete_bug': {'type': 'object', 'properties': {'bug_id': {'type': 'integer'}}, 'required': ['bug_id']},
            'mark_invalid': {'type': 'object', 'properties': {'bug_id': {'type': 'integer'}, 'reason': {'type': 'string'}}, 'required': ['bug_id']},
            'increment_score': {'type': 'object', 'properties': {'bug_id': {'type': 'integer'}, 'dimension': {'type': 'string'}, 'delta': {'type': 'number'}}, 'required': ['bug_id']},
            'get_bug_detail': {'type': 'object', 'properties': {'bug_id': {'type': 'integer'}}, 'required': ['bug_id']},
            'list_bugs': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'order_by': {'type': 'string'},
                    'limit': {'type': 'integer'},
                    'offset': {'type': 'integer'},
                },
            },
            'count_bugs': {'type': 'object', 'properties': {}},
            'get_metadata': {'type': 'object', 'properties': {'key': {'type': 'string'}}, 'required': ['key']},
            'set_metadata': {'type': 'object', 'properties': {'key': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['key', 'value']},
            'get_last_organize_time': {'type': 'object', 'properties': {}},
            'set_last_organize_time': {'type': 'object', 'properties': {}},
            'check_organize_reminder': {'type': 'object', 'properties': {'days_threshold': {'type': 'integer'}}},
            'search_by_keyword': {'type': 'object', 'properties': {'keyword': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['keyword']},
            'search_by_tag': {'type': 'object', 'properties': {'tag': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['tag']},
            'search_recent': {'type': 'object', 'properties': {'days': {'type': 'integer'}, 'limit': {'type': 'integer'}}},
            'search_high_score': {'type': 'object', 'properties': {'min_score': {'type': 'number'}, 'limit': {'type': 'integer'}}},
            'search_top_critical': {'type': 'object', 'properties': {'limit': {'type': 'integer'}}},
            'search_recent_unverified': {'type': 'object', 'properties': {'days': {'type': 'integer'}, 'limit': {'type': 'integer'}}},
            'search_by_status_and_score': {
                'type': 'object',
                'properties': {
                    'status': {'type': 'string'},
                    'min_score': {'type': 'number'},
                    'max_score': {'type': 'number'},
                    'verified': {'type': 'boolean'},
                    'order_by': {'type': 'string'},
                    'limit': {'type': 'integer'},
                },
            },
            # 'recall_by_path': {'type': 'object', 'properties': {'file_path': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['file_path']},
            # 'recall_by_path_full': {'type': 'object', 'properties': {'file_path': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['file_path']},
            'recall_by_pattern': {'type': 'object', 'properties': {'pattern': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['pattern']},
            'recall_by_path_for_hook': {'type': 'object', 'properties': {'file_path': {'type': 'string'}, 'transcript_path': {'type': 'string'}, 'limit': {'type': 'integer', 'default': 10}}, 'required': ['file_path', 'transcript_path']},
            'get_impacted_bugs': {'type': 'object', 'properties': {'file_path': {'type': 'string'}, 'limit': {'type': 'integer'}}, 'required': ['file_path']},
            'get_bug_impacts': {'type': 'object', 'properties': {'bug_id': {'type': 'integer'}}, 'required': ['bug_id']},
            'add_impact': {
                'type': 'object',
                'properties': {
                    'source_bug_id': {'type': 'integer'},
                    'impacted_path': {'type': 'string'},
                    'impact_type': {'type': 'string'},
                    'description': {'type': 'string'},
                    'severity': {'type': 'integer'},
                },
                'required': ['source_bug_id', 'impacted_path'],
            },
            'analyze_impact_patterns': {'type': 'object', 'properties': {'limit': {'type': 'integer'}}},
            'update_impacted_paths': {'type': 'object', 'properties': {'old_path': {'type': 'string'}, 'new_path': {'type': 'string'}}, 'required': ['old_path', 'new_path']},
            'delete_impact': {'type': 'object', 'properties': {'impact_id': {'type': 'integer'}, 'prevention_delta': {'type': 'number'}}, 'required': ['impact_id', 'prevention_delta']},
            'list_unverified_old': {'type': 'object', 'properties': {'days': {'type': 'integer'}, 'limit': {'type': 'integer'}}},
            'check_path_valid': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'root': {'type': 'string'}}},
            'check_bug_paths': {'type': 'object', 'properties': {'bug_id': {'type': 'integer'}}, 'required': ['bug_id']},
            # 'migrate_bug_paths_after_refactor': {'type': 'object', 'properties': {'old_path': {'type': 'string'}, 'new_path': {'type': 'string'}}, 'required': ['old_path', 'new_path']},
            'migrate_from_bash_command': {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']},
        }
        return schemas.get(tool_name, {'type': 'object', 'properties': {}})

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用工具"""
        # 移除前缀
        if tool_name.startswith('mcp__bug_book__'):
            tool_name = tool_name[15:]

        try:
            result = self._call(tool_name, arguments)

            # hook handler 已返回 {content, additionalContext} 格式，直接返回
            if isinstance(result, dict) and 'additionalContext' in result:
                return result

            # 统一格式化输出（兼容 SQLite 和 JSONL）
            result = self._normalize_result(tool_name, result)

            return {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:
            return {'content': [{'type': 'text', 'text': f'Error: {str(e)}'}], 'isError': True}

    def _call(self, tool_name: str, args: dict):
        """实际调用函数（通过后端实例）"""
        # 映射到后端实例的方法
        functions = {
            'add_bug': lambda: self.backend.add_bug(**args),
            'update_bug': lambda: self.backend.update_bug(args['bug_id'], **{k: v for k, v in args.items() if k != 'bug_id'}),
            'delete_bug': lambda: self.backend.delete_bug(args['bug_id']),
            'mark_invalid': lambda: self.backend.mark_invalid(args['bug_id'], args.get('reason')),
            'increment_score': lambda: self.backend.increment_score(args['bug_id'], args.get('dimension', 'occurrences'), args.get('delta', 1.0)),
            'get_bug_detail': lambda: self.backend.get_bug_detail(args['bug_id']),
            'list_bugs': lambda: self.backend.list_bugs(args.get('status'), args.get('order_by', 'score'), args.get('limit', 50), args.get('offset', 0)),
            'count_bugs': lambda: self.backend.count_bugs(),
            'search_by_keyword': lambda: self.backend.search_by_keyword(args['keyword'], args.get('limit', 20)),
            'search_by_tag': lambda: self.backend.search_by_tag(args['tag'], args.get('limit', 20)),
            'search_recent': lambda: self.backend.search_recent(args.get('days', 7), args.get('limit', 20)),
            'search_high_score': lambda: self.backend.search_high_score(args.get('min_score', 30.0), args.get('limit', 20)),
            'search_top_critical': lambda: self.backend.search_top_critical(args.get('limit', 20)),
            'search_recent_unverified': lambda: self.backend.search_recent_unverified(args.get('days', 7), args.get('limit', 20)),
            'search_by_status_and_score': lambda: self.backend.search_by_status_and_score(
                args.get('status', 'active'), args.get('min_score', 0.0), args.get('max_score'),
                args.get('verified'), args.get('order_by', 'score'), args.get('limit', 20)
            ),
            # 'recall_by_path': lambda: self.backend.recall_by_path(args['file_path'], args.get('limit', 10)),
            # 'recall_by_path_full': lambda: self.backend.recall_by_path_full(args['file_path'], args.get('limit', 10)),
            'recall_by_pattern': lambda: self.backend.recall_by_pattern(args['pattern'], args.get('limit', 10)),
            'recall_by_path_for_hook': lambda: self._handle_recall_for_hook(args['file_path'], args['transcript_path'], args.get('limit', 10)),
            'get_impacted_bugs': lambda: self.backend.get_impacted_bugs(args['file_path'], args.get('limit', 10)),
            'get_bug_impacts': lambda: self.backend.get_bug_impacts(args['bug_id']),
            'add_impact': lambda: self.backend.add_impact(
                args['source_bug_id'], args['impacted_path'], args.get('impact_type', 'regression'),
                args.get('description'), args.get('severity', 5)
            ),
            'analyze_impact_patterns': lambda: self.backend.analyze_impact_patterns(args.get('limit', 10)),
            'update_impacted_paths': lambda: self.backend.update_impacted_paths(args['old_path'], args['new_path']),
            'delete_impact': lambda: self.backend.delete_impact(args['impact_id'], args['prevention_delta']),
            'list_unverified_old': lambda: self.backend.list_unverified_old(args.get('days', 30), args.get('limit', 20)),
            'check_path_valid': lambda: self.backend.check_path_valid(args['path'], args.get('root')),
            'check_bug_paths': lambda: self.backend.check_bug_paths(args['bug_id']),
            # 'migrate_bug_paths_after_refactor': lambda: self.backend.migrate_bug_paths_after_refactor(args['old_path'], args['new_path']),
            'migrate_from_bash_command': lambda: self._handle_migrate_from_command(args['command']),
        }

        func = functions.get(tool_name)
        if not func:
            raise ValueError(f'Unknown tool: {tool_name}')

        return func()

    def _normalize_result(self, tool_name: str, result):
        """统一格式化输出（兼容 SQLite 和 JSONL）"""
        if result is None:
            return result
        
        # get_bug_detail: 转换 scores 格式
        if tool_name == 'get_bug_detail' and isinstance(result, dict):
            scores = result.get('scores', {})
            if isinstance(scores, list):
                result['scores'] = {dim: val for dim, val in scores}
            return result
        
        # 列表类型：统一 bug 摘要格式
        list_tools = {
            'list_bugs', 'search_by_keyword', 'search_by_tag',
            'search_recent', 'search_high_score', 'search_top_critical',
            'search_recent_unverified', 'search_by_status_and_score',
            'recall_by_path', 'recall_by_pattern', 'get_impacted_bugs',
            'list_unverified_old'
        }
        
        if tool_name in list_tools and isinstance(result, list):
            return [self._normalize_bug_summary(bug) for bug in result]
        
        return result
    
    def _normalize_bug_summary(self, bug: dict) -> dict:
        """统一 bug 摘要格式（确保所有字段存在）"""
        return {
            'id': bug.get('id'),
            'title': str(bug.get('title', '')),
            'phenomenon': str(bug.get('phenomenon', '')),
            'score': bug.get('score', 0),
            'status': str(bug.get('status', 'active')),
            'verified': bug.get('verified', False),
            'created_at': str(bug.get('created_at', '')),
        }

    def _handle_recall_for_hook(self, file_path: str, transcript_path: str, limit: int):
        """为Hook返回additionalContext格式"""
        # 1. 检查是否在最近 10 轮内已召回
        if self._has_recent_recall(transcript_path, file_path, lookback=10):
            return {
                "content": [{"type": "text", "text": ""}],
                "additionalContext": ""
            }

        # 2. 调用后端召回
        result = self.backend.recall_by_path_full(file_path, limit=limit)

        related = result.get("related_bugs", [])
        impacted = result.get("impacted_by", [])
        all_bugs = related + impacted
        if not all_bugs:
            return {
                "content": [{"type": "text", "text": ""}],
                "additionalContext": ""
            }

        # 3. 格式化输出，在 content 中写入标记供后续检查
        message = f"📋 相关 Bug 召回（{len(all_bugs)}条）：\n\n"
        for bug in all_bugs:
            message += f"**Bug #{bug['id']}**: {bug['title']}\n"
            message += f"- Score: {bug['score']}\n"
            message += f"- Status: {bug.get('status', 'unknown')}\n"
            phenomenon = bug.get('phenomenon', '') or ''
            if phenomenon:
                message += f"- Phenomenon: {phenomenon[:150]}\n"
            root_cause = bug.get('root_cause', '') or ''
            if root_cause:
                message += f"- Root Cause: {root_cause[:150]}\n"
            solution = bug.get('solution', '') or ''
            if solution:
                message += f"- Solution: {solution[:150]}\n"
            message += "\n"

        recall_tag = "已召回 " + str(len(all_bugs)) + " 个相关 bug [recall " + file_path + "]"
        return {
            "content": [{"type": "text", "text": recall_tag}],
            "additionalContext": message
        }

    def _has_recent_recall(self, transcript_path: str, file_path: str, lookback: int = 10) -> bool:
        """检查 transcript 中最近 N 轮是否已有该 path 的 recall"""
        try:
            path = Path(transcript_path)
            if not path.exists():
                return False

            with open(path, 'r') as f:
                transcript = json.load(f)

            # 检查最近 lookback 轮对话
            messages = transcript.get('messages', [])[-lookback * 2:]

            for msg in messages:
                if msg.get('role') == 'assistant':
                    content = msg.get('content', '')
                    if f'[recall ' + file_path + ']' in content:
                        return True

            return False
        except Exception:
            return False

    def _handle_migrate_from_command(self, command: str):
        """从Bash命令提取路径并迁移"""
        import re
        
        # 提取 mv 或 git mv 命令的路径
        match = re.search(r'(?:git\s+)?mv\s+(\S+)\s+(\S+)', command)
        if not match:
            return {
                "content": [{"type": "text", "text": "未检测到有效的mv命令"}],
                "additionalContext": ""
            }
        
        old_path, new_path = match.groups()

        # 调用后端迁移
        migrated_bugs, impacted_count = self.backend.migrate_bug_paths_after_refactor(old_path, new_path)

        migrated_count = impacted_count
        summary = f"🔄 路径迁移完成，影响 {migrated_count} 个 bug 记录"
        detail = f"路径 `{old_path}` → `{new_path}` 已更新，{migrated_count} 个 bug 的 paths/recalls 已同步迁移"

        return {
            "content": [{"type": "text", "text": summary}],
            "additionalContext": detail
        }


# ---------------------------------------------------------------------------
# MCP Server 入口点（stdio 协议）
# ---------------------------------------------------------------------------

def main():
    server = MCPServer()

    # MCP stdio 协议循环
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = server.handle_request(request)
            if response is not None:
                print(json.dumps(response), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({'error': {'code': -32700, 'message': 'Invalid JSON'}}), flush=True)
        except Exception as e:
            print(json.dumps({'error': {'code': -32603, 'message': str(e)}}), flush=True)


if __name__ == '__main__':
    main()