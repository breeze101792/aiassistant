from modules.eyes.eyes import EyesModule
from modules.eyes.vision_backends.stub import StubVision
from modules.eyes.vision_backends.base import VisionBackend
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
