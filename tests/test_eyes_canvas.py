import tempfile
import os

from modules.eyes.eyes import EyesModule
from modules.eyes.vision_backends.stub import StubVision
from modules.eyes.vision_backends.base import VisionBackend
from modules.canvas.canvas import CanvasModule
from modules.canvas.backends.file import FileCanvas
from modules.canvas.backends.base import CanvasBackend
from bus.bus import MessageBus


class TestStubVision:
    def test_capture_returns_placeholder(self):
        stub = StubVision()
        result = stub.capture()
        assert 'description' in result
        assert 'objects' in result
        assert 'image_base64' in result

    def test_analyze_returns_placeholder(self):
        stub = StubVision()
        result = stub.analyze('fake_base64')
        assert 'description' in result

    def test_is_instance_of_base(self):
        assert isinstance(StubVision(), VisionBackend)


class TestEyesModule:
    def test_module_name(self):
        bus = MessageBus()
        eyes = EyesModule(bus, {'backend': 'stub'})
        assert eyes.module_name == 'eyes'

    def test_stub_backend_selected(self):
        bus = MessageBus()
        eyes = EyesModule(bus, {'backend': 'stub'})
        assert eyes.backend_name == 'stub'


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
