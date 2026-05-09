#!/usr/bin/env python3
"""MCP Server 端到端测试 - 通过 stdio 协议真实通信"""

import json
import subprocess
import sys
import os
from pathlib import Path


def run_mcp_test(storage_type: str):
    """通过子进程运行 MCP Server 并测试"""
    print(f"\n{'='*60}")
    print(f"测试 {storage_type.upper()} 后端 (MCP stdio)")
    print('='*60)
    
    # 启动 MCP Server 子进程
    env = os.environ.copy()
    env['BUG_BOOK_STORAGE'] = storage_type
    
    # Windows 下需要特殊处理
    creationflags = 0
    if sys.platform == 'win32':
        import subprocess as sp
        creationflags = sp.CREATE_NO_WINDOW
    
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent.parent / 'mcp' / 'mcp_server.py')],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
        creationflags=creationflags
    )
    
    errors = []
    request_id = 0
    
    def send_request(method: str, params: dict = None):
        """发送 MCP 请求"""
        nonlocal request_id
        request_id += 1
        
        request = {
            'jsonrpc': '2.0',
            'id': request_id,
            'method': method,
            'params': params or {}
        }
        
        proc.stdin.write(json.dumps(request) + '\n')
        proc.stdin.flush()
        
        # 读取响应
        response_line = proc.stdout.readline()
        if not response_line:
            raise Exception("MCP Server 未响应")
        
        response = json.loads(response_line)
        
        if 'error' in response:
            raise Exception(response['error'].get('message', 'Unknown error'))
        
        return response.get('result')
    
    def call_tool(tool_name: str, arguments: dict = None):
        """调用 MCP tool"""
        result = send_request('tools/call', {
            'name': f'mcp__bug_book__{tool_name}',
            'arguments': arguments or {}
        })
        
        # 解析返回的 JSON 字符串
        if isinstance(result, dict) and 'content' in result:
            content = result['content'][0]['text']
            if not content or content.strip() == '':
                return []  # 空响应返回空列表
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                raise Exception(f"Invalid JSON response: {content[:100]}")
        return result
    
    def test(name, func):
        """执行测试"""
        try:
            result = func()
            print(f"✓ {name}: {str(result)[:100]}")
            return result
        except Exception as e:
            print(f"✗ {name}: {e}")
            errors.append((name, str(e)))
            return None
    
    try:
        # 初始化
        test("initialize", lambda: send_request('initialize'))
        test("tools/list", lambda: send_request('tools/list'))
        
        # ============================================================
        # 1. CRUD 操作
        # ============================================================
        add_result = test("add_bug", lambda: call_tool('add_bug', {
            'title': '测试Bug',
            'phenomenon': '测试现象',
            'root_cause': '测试根因',
            'solution': '测试方案',
            'paths': ['test.py:10'],
            'tags': ['test'],
            'keywords': ['测试']
        }))
        
        if add_result is None or len(add_result) < 2:
            print(f"\n{storage_type.upper()} 后端基础功能失败")
            return errors
        
        bug_id = add_result[0]
        
        test("get_bug_detail", lambda: call_tool('get_bug_detail', {'bug_id': bug_id}))
        test("count_bugs", lambda: call_tool('count_bugs'))
        test("list_bugs", lambda: call_tool('list_bugs', {'limit': 5}))
        
        test("update_bug", lambda: call_tool('update_bug', {'bug_id': bug_id, 'title': '更新后的标题'}))
        test("increment_score", lambda: call_tool('increment_score', {'bug_id': bug_id, 'dimension': 'occurrences', 'delta': 1.0}))
        test("mark_invalid", lambda: call_tool('mark_invalid', {'bug_id': bug_id, 'reason': '测试标记失效'}))
        
        # ============================================================
        # 3. 影响关系管理
        # ============================================================
        impact_result = test("add_impact", lambda: call_tool('add_impact', {
            'source_bug_id': bug_id,
            'impacted_path': 'affected.py',
            'impact_type': 'regression',
            'description': '测试影响',
            'severity': 7
        }))
        
        test("get_bug_impacts", lambda: call_tool('get_bug_impacts', {'bug_id': bug_id}))
        test("get_impacted_bugs", lambda: call_tool('get_impacted_bugs', {'file_path': 'affected.py'}))
        test("analyze_impact_patterns", lambda: call_tool('analyze_impact_patterns', {'limit': 10}))
        
        if impact_result and isinstance(impact_result, (list, tuple)) and len(impact_result) > 0:
            impact_id = impact_result[0]
            test("delete_impact", lambda: call_tool('delete_impact', {'impact_id': impact_id, 'prevention_delta': 1.0}))
        elif impact_result and isinstance(impact_result, int):
            # add_impact 返回的是 impact_id（整数）
            test("delete_impact", lambda: call_tool('delete_impact', {'impact_id': impact_result, 'prevention_delta': 1.0}))
        
        # 重新添加影响用于后续测试
        test("add_impact_for_update", lambda: call_tool('add_impact', {
            'source_bug_id': bug_id,
            'impacted_path': 'old/path.py',
            'impact_type': 'side_effect',
            'severity': 5
        }))
        test("update_impacted_paths", lambda: call_tool('update_impacted_paths', {
            'old_path': 'old/path.py',
            'new_path': 'new/path.py'
        }))
        
        # ============================================================
        # 4. 搜索功能
        # ============================================================
        test("search_by_keyword", lambda: call_tool('search_by_keyword', {'keyword': '测试'}))
        test("search_by_tag", lambda: call_tool('search_by_tag', {'tag': 'test'}))
        test("search_recent", lambda: call_tool('search_recent', {'days': 7, 'limit': 10}))
        test("search_high_score", lambda: call_tool('search_high_score', {'min_score': 0, 'limit': 10}))
        test("search_top_critical", lambda: call_tool('search_top_critical', {'limit': 5}))
        test("search_recent_unverified", lambda: call_tool('search_recent_unverified', {'days': 7, 'limit': 10}))
        test("search_by_status_and_score", lambda: call_tool('search_by_status_and_score', {
            'status': 'active',
            'min_score': 0,
            'max_score': 100,
            'limit': 10
        }))
        
        # ============================================================
        # 5. 召回功能
        # ============================================================
        test("recall_by_path", lambda: call_tool('recall_by_path', {'file_path': 'test.py', 'limit': 10}))
        test("recall_by_path_full", lambda: call_tool('recall_by_path_full', {'file_path': 'test.py', 'limit': 10}))
        test("recall_by_pattern", lambda: call_tool('recall_by_pattern', {'pattern': 'test/*', 'limit': 10}))
        
        # ============================================================
        # 6. 高级功能
        # ============================================================
        test("list_unverified_old", lambda: call_tool('list_unverified_old', {'days': 30, 'limit': 10}))
        test("check_path_valid", lambda: call_tool('check_path_valid', {'path': 'test.py'}))
        test("migrate_bug_paths_after_refactor", lambda: call_tool('migrate_bug_paths_after_refactor', {
            'old_path': 'test.py',
            'new_path': 'migrated/test.py'
        }))
        
        # ============================================================
        # 清理
        # ============================================================
        test("delete_bug", lambda: call_tool('delete_bug', {'bug_id': bug_id}))
        
    finally:
        # 关闭进程
        proc.terminate()
        proc.wait(timeout=5)
    
    print(f"\n{storage_type.upper()} 后端测试结果: {len(errors)} 个错误")
    for name, error in errors:
        print(f"  - {name}: {error}")
    
    return errors


def main():
    print("="*60)
    print("MCP Server 端到端测试")
    print("="*60)
    
    # 测试 SQLite 后端
    sqlite_errors = run_mcp_test("sqlite")
    
    # 测试 JSONL 后端
    jsonl_errors = run_mcp_test("jsonl")
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print('='*60)
    print(f"SQLite 后端: {len(sqlite_errors)} 个错误")
    print(f"JSONL 后端: {len(jsonl_errors)} 个错误")
    
    if sqlite_errors:
        print("\nSQLite 错误详情:")
        for name, error in sqlite_errors:
            print(f"  - {name}: {error}")
    
    if jsonl_errors:
        print("\nJSONL 错误详情:")
        for name, error in jsonl_errors:
            print(f"  - {name}: {error}")
    
    total_errors = len(sqlite_errors) + len(jsonl_errors)
    if total_errors == 0:
        print("\n✓ 所有测试通过！MCP Server 双后端完全兼容")
    else:
        print(f"\n✗ 共 {total_errors} 个错误需要修复")
    
    return total_errors


if __name__ == '__main__':
    sys.exit(main())
