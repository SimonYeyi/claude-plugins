#!/usr/bin/env python3
"""bug-book MCP Server：提供所有 bug 操作的 MCP tool"""

import json
import sys
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

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
                        'tools': { 'listChanged': False },
                    },
                    'serverInfo': {
                        'name': 'bug-book',
                        'version': '1.0.0'
                    }
                }
            }
        elif method == 'tools/list':
            return {'jsonrpc': '2.0', 'id': request_id, 'result': { 'tools': self.list_tools() }}
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
            # 1. save_bugs - 统一保存接口（支持批量）
            self._tool('save_bugs', '保存 Bug（新增、更新或删除，支持批量）',
                '保存 Bug（新增、更新或删除），支持批量操作。\n\n'
                '触发场景：\n'
                '- 整理错题集时修正 bug 详情（如标记失效、更新路径、修改状态等）\n'
                '注意：日常新增 bug 由 skill 自动完成，无需手动调用此工具。'),
            
            # 2. get_bug_detail - 获取详情
            self._tool('get_bug_detail', '获取 bug 详情',
                '获取 bug 的完整信息，包括 scores、paths、tags、recalls、impacts 等。\n\n'
                '触发场景：\n'
                '- 需要获取 bug 的详细信息（如“bug #5 的解决方案是什么”）\n'
                '- 需要查看 bug 的具体字段信息\n'),
            
            # 3. search_bugs - 统一搜索
            self._tool('search_bugs', '统一搜索',
                '统一搜索接口，支持多种搜索模式和分页。\n\n'
                '触发场景：\n'
                '- 搜索/查找 bug（如"查一下 session 相关的 bug"）\n'
                '- 查询特定模块的问题（使用 module 模式）\n'
                '- 查看高分/未验证 bugs\n'),
                        
            # 4. organize_bugs - 整理错题集
            self._tool('organize_bugs', '整理错题集',
                '整理 bug-book 数据库，执行以下操作：\n'
                '1. 压缩文件（移除已删除记录，相同ID只保留最后一条）\n'
                '2. 检查路径有效性（标记失效路径）\n'
                '3. 检查长期未验证记录（超过30天）\n'
                '4. 生成整理报告和统计信息\n\n'
                '触发场景：\n'
                '- 用户明确要求整理（如"帮我整理一下错题集"）\n'
                '- 用户要求清理失效条目或归类重复问题\n'
                '- 定期检查维护（建议每周一次）\n\n'
                '注意：此操作不会自动修改数据，只返回整理报告和建议。'),
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
            'save_bugs': {
                'type': 'array',
                'description': '保存 Bug（新增、更新或删除），支持批量操作。\n\n'
                    '触发场景：\n'
                    '- 整理错题集时修正 bug 详情（如标记失效、更新路径、修改状态等）\n'
                    '- 批量处理多个 bug（如批量标记失效、批量更新分数）\n\n'
                    '注意：日常新增 bug 由 skill 自动完成，无需手动调用此工具。',
                'items': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer', 'description': 'Bug ID（所有 mode 必填）'},
                        'mode': {
                            'type': 'string',
                            'enum': [
                                'add', 'update_fields', 'delete',
                                'add_impacts', 'remove_impacts', 'replace_impacts',
                                'add_paths', 'remove_paths', 'replace_paths', 'update_paths',
                                'add_recalls', 'remove_recalls', 'replace_recalls',
                                'increment_scores', 'decrement_scores', 'replace_scores',
                            ],
                            'description': '操作模式：add(新增)/update_fields(更新字段)/delete(删除)/add_impacts(添加影响)/remove_impacts(移除影响)/replace_impacts(替换影响)/add_paths(添加路径)/remove_paths(移除路径)/replace_paths(替换路径)/update_paths(更新路径)/add_recalls(添加召回)/remove_recalls(移除召回)/replace_recalls(替换召回)/increment_scores(累加分数)/decrement_scores(扣减分数)/replace_scores(替换分数)'
                        },
                        'title': {'type': 'string', 'description': '标题（add 模式必填）'},
                        'phenomenon': {'type': 'string', 'description': '现象描述（add 模式必填）'},
                        'root_cause': {'type': 'string', 'description': '根本原因（update_fields 模式可选）'},
                        'solution': {'type': 'string', 'description': '解决方案（update_fields 模式可选）'},
                        'test_case': {'type': 'string', 'description': '测试用例（update_fields 模式可选）'},
                        'status': {'type': 'string', 'enum': ['active', 'resolved', 'invalid'], 'description': '状态（update_fields 模式可选）'},
                        'verified': {'type': 'boolean', 'description': '是否验证（update_fields 模式可选）'},
                        'verified_at': {'type': 'string', 'description': '验证时间（update_fields 模式可选）'},
                        'verified_by': {'type': 'string', 'description': '验证人（update_fields 模式可选）'},
                        
                        'impacts': {
                            'type': 'array',
                            'description': '影响关系数组（add_impacts/replace_impacts 模式必填）',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'solution_change': {'type': 'string', 'description': '解决方案变更'},
                                    'impact_description': {'type': 'string', 'description': '影响描述'},
                                    'impact_type': {'type': 'string', 'enum': ['regression', 'side_effect', 'dependency'], 'description': '影响类型'},
                                    'severity': {'type': 'integer', 'minimum': 0, 'maximum': 10, 'description': '严重程度（0-10）'},
                                },
                                'required': ['solution_change', 'impact_description', 'impact_type', 'severity']
                            }
                        },
                        'impact_ids': {'type': 'array', 'items': {'type': 'integer'}, 'description': '要移除的影响关系ID数组（remove_impacts 模式必填）'},
                        
                        'paths': {
                            'type': 'array',
                            'description': '路径数组（add_paths/replace_paths/remove_paths 模式必填）。remove_paths 时：传字符串删除整个文件，传{file, functions}对象只删除指定函数',
                            'items': {
                                'oneOf': [
                                    {'type': 'string'},
                                    {
                                        'type': 'object',
                                        'properties': {
                                            'file': {'type': 'string'},
                                            'functions': {'type': 'array', 'items': {'type': 'string'}},
                                        },
                                    }
                                ]
                            }
                        },
                        
                        'path_updates': {
                            'type': 'array',
                            'description': '路径更新数组（update_paths 模式必填），每项包含 old_path/new_path',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'old_path': {'type': 'string'},
                                    'new_path': {'type': 'string'},
                                },
                                'required': ['old_path', 'new_path'],
                            }
                        },
                        
                        'recalls': {'type': 'array', 'items': {'type': 'string'}, 'description': '召回模式数组（add_recalls/remove_recalls/replace_recalls 模式必填）'},
                        
                        'scores': {
                            'type': 'object',
                            'description': '分数字典（increment_scores/decrement_scores/replace_scores 模式必填）',
                            'properties': {
                                'importance': {'type': 'number', 'description': '重要性分数'},
                                'complexity': {'type': 'number', 'description': '复杂度分数'},
                                'scope': {'type': 'number', 'description': '影响范围分数'},
                                'difficulty': {'type': 'number', 'description': '修复难度分数'},
                                'occurrences': {'type': 'number', 'description': '出现次数分数'},
                                'emotion': {'type': 'number', 'description': '情绪影响分数'},
                                'prevention': {'type': 'number', 'description': '预防价值分数'},
                            },
                        },
                    },
                    'required': ['id', 'mode'],
                },
            },
            
            'get_bug_detail': {
                'type': 'object',
                'description': '获取 Bug 详情，包含完整的现象、根因、解决方案等信息',
                'properties': {'bug_id': {'type': 'integer'}},
                'required': ['bug_id'],
            },
            
            'search_bugs': {
                'type': 'object',
                'description': '统一搜索接口，支持多种搜索模式和分页',
                'properties': {
                    'mode': {
                        'type': 'string',
                        'enum': ['keyword', 'tag', 'recent', 'high_score', 'critical', 'unverified', 'custom', 'module'],
                        'description': '搜索模式：keyword(关键词)/tag(标签)/recent(最近)/high_score(高分)/critical(严重)/unverified(未验证)/custom(自定义)/module(模块召回)'
                    },
                    'keyword': {'type': 'string', 'description': '搜索关键词（keyword 模式必填）'},
                    'tag': {'type': 'string', 'description': '标签名称（tag 模式必填）'},
                    'days': {'type': 'integer', 'default': 7, 'description': '天数（recent/unverified 模式使用）'},
                    'min_score': {'type': 'number', 'description': '最低分数（high_score/custom 模式使用）'},
                    'max_score': {'type': 'number', 'description': '最高分数（custom 模式使用）'},
                    'status': {'type': 'string', 'enum': ['active', 'resolved', 'invalid'], 'description': '状态过滤（custom 模式使用）'},
                    'verified': {'type': 'boolean', 'description': '验证状态过滤（custom 模式使用）'},
                    'order_by': {'type': 'string', 'enum': ['score', 'created_at', 'updated_at'], 'default': 'score', 'description': '排序字段（custom 模式使用）'},
                    'pattern': {'type': 'string', 'description': '路径模式（module 模式必填，如 src/utils/*.ts）'},
                    'limit': {'type': 'integer', 'default': 20, 'minimum': 1, 'maximum': 100, 'description': '每页数量'},
                    'offset': {'type': 'integer', 'default': 0, 'minimum': 0, 'description': '偏移量'},
                },
                'required': ['mode'],
            },
            
            'organize_bugs': {
                'type': 'object',
                'description': '整理错题集：压缩文件、检查路径有效性、检查长期未验证记录、生成统计报告',
                'properties': {},
            },
        }
        return schemas.get(tool_name, {'type': 'object', 'properties': {}})

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用工具"""
        # 移除前缀
        if tool_name.startswith('mcp__bug_book__'):
            tool_name = tool_name[15:]

        try:
            result = self._call(tool_name, arguments)

            # 后端已返回 MCP 标准格式（含 content），直接返回
            if isinstance(result, dict) and 'content' in result:
                return result

            # 普通工具：JSON 序列化
            return {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}]}
        except Exception as e:
            return {'content': [{'type': 'text', 'text': f'Error: {str(e)}'}], 'isError': True}

    def _call(self, tool_name: str, args):
        """实际调用函数（通过后端实例）"""
        functions = {
            'save_bugs': lambda: self.backend.save_bugs(args),  # 直接传数组
            'get_bug_detail': lambda: self.backend.get_bug_detail(args['bug_id']),
            'search_bugs': lambda: self.backend.search_bugs(**args),
            'recall_for_hook': lambda: self._handle_recall_for_hook(args['file_path'], args['transcript_path'], args.get('limit', 10)),
            'migrate_path_for_hook': lambda: self._handle_migrate_path_for_hook(args['command']),
            'organize_bugs': lambda: self._handle_organize_bugs(),
        }

        func = functions.get(tool_name)
        if not func:
            raise ValueError(f'Unknown tool: {tool_name}')

        return func()

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

    def _handle_migrate_path_for_hook(self, command: str):
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
        detail = f"路径 `{old_path}` → `{new_path}` 已更新，{migrated_count} 个 bug 的 paths 已同步迁移"

        return {
            "content": [{"type": "text", "text": summary}],
            "additionalContext": detail
        }

    def _handle_organize_bugs(self):
        """整理错题集"""
        from metadata_store import metadata_store
        
        report_lines = []
        report_lines.append("# 📋 Bug-Book 整理报告\n")
        
        # === 第1步：压缩文件 ===
        removed_count = self.backend.compact_file()
        report_lines.append(f"## ✅ 第1步：文件压缩\n")
        report_lines.append(f"- 清理了 {removed_count} 条旧记录\n")
        report_lines.append(f"- 相同ID只保留最后一条记录\n\n")
        
        # === 第2步：检查路径有效性 ===
        # 检查所有非 invalid 的 bug（active + resolved）
        active_bugs = self.backend.list_bugs(status="active", limit=99999)
        resolved_bugs = self.backend.list_bugs(status="resolved", limit=99999)
        all_bugs = active_bugs + resolved_bugs
        
        invalid_path_bugs = []
        for bug in all_bugs:
            invalid_paths = self.backend.check_bug_paths(bug['id'])
            if invalid_paths:
                invalid_path_bugs.append({
                    'id': bug['id'],
                    'title': bug['title'],
                    'status': bug.get('status', 'active'),
                    'invalid_paths': invalid_paths
                })
        
        report_lines.append(f"## 🔍 第2步：路径有效性检查\n")
        if invalid_path_bugs:
            active_invalid = [b for b in invalid_path_bugs if b['status'] == 'active']
            resolved_invalid = [b for b in invalid_path_bugs if b['status'] == 'resolved']
            
            report_lines.append(f"发现 {len(invalid_path_bugs)} 个 bug 有无效路径：\n")
            report_lines.append(f"- 活跃 (active): {len(active_invalid)}\n")
            report_lines.append(f"- 已解决 (resolved): {len(resolved_invalid)}\n\n")
            
            for item in invalid_path_bugs:  # 全量展示
                paths_str = ', '.join([f'`{p}`' for p in item['invalid_paths']])
                status_tag = "🔴" if item['status'] == 'active' else "🟢"
                report_lines.append(
                    f"- {status_tag} **Bug #{item['id']}** [{item['status']}]: {item['title']}\n"
                    f"  - 无效路径: {paths_str}\n"
                )
            report_lines.append("\n💡 建议：标记这些 bug 为失效，或更新路径。\n\n")
        else:
            report_lines.append("✅ 所有路径均有效\n\n")
        
        # === 第3步：检查长期未验证记录 ===
        unverified_old = self.backend.list_unverified_old(days=30, limit=99999)  # 不限制，返回所有
        report_lines.append(f"## ⏳ 第3步：长期未验证记录（超过30天）\n")
        if unverified_old:
            report_lines.append(f"发现 {len(unverified_old)} 条长期未验证记录：\n")
            for bug in unverified_old:  # 全量展示
                report_lines.append(
                    f"- **Bug #{bug['id']}**: {bug['title']} - "
                    f"创建于 {bug['created_at'][:10]}（{bug.get('score', 0):.1f}分）\n"
                )
            report_lines.append("\n💡 建议：确认是否已修复？如已修复请验证，如功能已废弃请标记失效。\n\n")
        else:
            report_lines.append("✅ 没有长期未验证的记录\n\n")
        
        # === 第4步：数据库统计 ===
        total_count = self.backend.count_bugs()
        
        report_lines.append(f"## 📈 第4步：数据库统计\n")
        report_lines.append(f"- 总记录数: {total_count}\n")
        report_lines.append(f"- 活跃 (active): {len(active_bugs)}\n")
        report_lines.append(f"- 已解决 (resolved): {len(resolved_bugs)}\n\n")
        
        # === 设置最后整理时间 ===
        metadata_store.set_last_organize_time()
        report_lines.append("---\n")
        report_lines.append(f"✅ 整理完成！最后整理时间已更新。\n")
        
        # 返回报告
        full_report = ''.join(report_lines)
        return {
            "content": [{"type": "text", "text": full_report}],
            "additionalContext": full_report
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
