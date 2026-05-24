import tempfile
import os

from modules.hands.builtin_tools.datetime_tool import DateTimeTool
from modules.hands.builtin_tools.file_ops import FileReadTool, FileWriteTool, FileListTool
from modules.hands.builtin_tools.websearch import WebSearchTool
from modules.hands.builtin_tools.webfetch import WebFetchTool
from modules.hands.builtin_tools.weather import WeatherTool
from modules.hands.builtin_tools.base import ToolBase
from modules.hands.sandbox import Sandbox


class TestToolBase:
    def test_interface(self):
        assert hasattr(ToolBase, 'name')
        assert hasattr(ToolBase, 'description')
        assert hasattr(ToolBase, 'parameters')
        assert hasattr(ToolBase, 'execute')


class TestDateTimeTool:
    def test_execute_returns_expected_keys(self):
        tool = DateTimeTool()
        result = tool.execute()
        assert 'iso' in result
        assert 'date' in result
        assert 'time' in result
        assert 'timezone' in result
        assert 'day_of_week' in result

    def test_schema_is_valid(self):
        tool = DateTimeTool()
        assert tool.parameters['type'] == 'object'
        assert tool.parameters['required'] == []


class TestFileOps:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    def test_write_and_read(self):
        path = os.path.join(self.tmp, 'test.txt')
        fw = FileWriteTool()
        result = fw.execute(path=path, content='hello world')
        assert result['bytes_written'] == 11

        fr = FileReadTool()
        content = fr.execute(path=path)
        assert content == 'hello world'

    def test_read_nonexistent_raises(self):
        fr = FileReadTool()
        with __import__('pytest').raises(FileNotFoundError):
            fr.execute(path='/nonexistent/file.txt')

    def test_list_directory(self):
        os.makedirs(os.path.join(self.tmp, 'sub'))
        fl = FileListTool()
        files = fl.execute(path=self.tmp)
        assert 'sub' in files


class TestSandbox:
    def test_run_command(self):
        sb = Sandbox(safe_paths=[tempfile.gettempdir()], timeout=5)
        result = sb.run('echo hello')
        assert result['returncode'] == 0
        assert 'hello' in result['stdout']

    def test_safe_path_check(self):
        sb = Sandbox(safe_paths=['/tmp/safe'])
        assert sb._is_safe_path('/tmp/safe/file.txt')
        assert not sb._is_safe_path('/etc/passwd')


class TestWebSearch:
    def test_has_interface(self):
        tool = WebSearchTool()
        assert tool.name == 'web_search'
        assert 'query' in tool.parameters.get('properties', {})


class TestWebFetch:
    def test_fetch_httpbin(self):
        tool = WebFetchTool()
        result = tool.execute(url='https://httpbin.org/get')
        assert result is not None
        assert len(result) > 0
