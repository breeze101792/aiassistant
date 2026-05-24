import tempfile
import os

from modules.canvas.canvas import CanvasModule
from modules.canvas.backends.file import FileCanvas
from modules.canvas.backends.base import CanvasBackend
from bus.bus import MessageBus


class TestFileCanvas:
    def test_show_text_creates_file(self):
        tmp = tempfile.mkdtemp()
        fc = FileCanvas(output_dir=tmp)
        fc.show(content_type='text', data='Hello canvas', title='Test')
        files = os.listdir(tmp)
        assert len(files) > 0

    def test_clear_removes_files(self):
        tmp = tempfile.mkdtemp()
        fc = FileCanvas(output_dir=tmp)
        fc.show(content_type='text', data='test')
        assert len(os.listdir(tmp)) > 0
        fc.clear()
        assert len(os.listdir(tmp)) == 0

    def test_is_instance_of_base(self):
        assert isinstance(FileCanvas(), CanvasBackend)


class TestCanvasModule:
    def test_module_name(self):
        bus = MessageBus()
        canvas = CanvasModule(bus, {'backend': 'file'})
        assert canvas.module_name == 'canvas'

    def test_file_backend_selected(self):
        bus = MessageBus()
        canvas = CanvasModule(bus, {'backend': 'file'})
        assert canvas.backend_name == 'file'
