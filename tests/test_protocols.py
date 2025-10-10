import multibase
import multihash
import pytest
import varint

from multiaddr import Multiaddr, exceptions, protocols
from multiaddr.codecs import certhash, http_path, ipcidr, memory
from multiaddr.exceptions import BinaryParseError, StringParseError


def test_code_to_varint():
    vi = varint.encode(5)
    assert vi == b"\x05"
    vi = varint.encode(150)
    assert vi == b"\x96\x01"


def test_varint_to_code():
    cc = varint.decode_bytes(b"\x05")
    assert cc == 5
    cc = varint.decode_bytes(b"\x96\x01")
    assert cc == 150


@pytest.fixture
def valid_params():
    return {"code": protocols.P_IP4, "name": "ipb4", "codec": "ipb"}


def test_valid(valid_params):
    proto = protocols.Protocol(**valid_params)
    for key in valid_params:
        assert getattr(proto, key) == valid_params[key]


@pytest.mark.parametrize("invalid_code", ["abc"])
def test_invalid_code(valid_params, invalid_code):
    valid_params["code"] = invalid_code
    with pytest.raises(TypeError):
        protocols.Protocol(**valid_params)


@pytest.mark.parametrize("invalid_name", [123, 1.0])
def test_invalid_name(valid_params, invalid_name):
    valid_params["name"] = invalid_name
    with pytest.raises(TypeError):
        protocols.Protocol(**valid_params)


@pytest.mark.parametrize("invalid_codec", [b"ip4", 123, 0.123])
def test_invalid_codec(valid_params, invalid_codec):
    valid_params["codec"] = invalid_codec
    with pytest.raises(TypeError):
        protocols.Protocol(**valid_params)


@pytest.mark.parametrize("name", ["foo-str", "foo-u"])
def test_valid_names(valid_params, name):
    valid_params["name"] = name
    test_valid(valid_params)


@pytest.mark.parametrize("codec", ["ip4", "ip6"])
def test_valid_codecs(valid_params, codec):
    valid_params["codec"] = codec
    test_valid(valid_params)


def test_protocol_with_name():
    proto = protocols.protocol_with_name("ip4")
    assert proto.name == "ip4"
    assert proto.code == protocols.P_IP4
    assert proto.size == 32
    assert proto.vcode == varint.encode(protocols.P_IP4)
    assert protocols.protocol_with_any("ip4") == proto
    assert protocols.protocol_with_any(proto) == proto

    with pytest.raises(exceptions.ProtocolNotFoundError):
        proto = protocols.protocol_with_name("foo")


def test_protocol_with_code():
    proto = protocols.protocol_with_code(protocols.P_IP4)
    assert proto.name == "ip4"
    assert proto.code == protocols.P_IP4
    assert proto.size == 32
    assert proto.vcode == varint.encode(protocols.P_IP4)
    assert protocols.protocol_with_any(protocols.P_IP4) == proto
    assert protocols.protocol_with_any(proto) == proto

    with pytest.raises(exceptions.ProtocolNotFoundError):
        proto = protocols.protocol_with_code(1234)


def test_protocol_equality():
    proto1 = protocols.protocol_with_name("ip4")
    proto2 = protocols.protocol_with_code(protocols.P_IP4)
    proto3 = protocols.protocol_with_name("onion")
    proto4 = protocols.protocol_with_name("onion3")

    assert proto1 == proto2
    assert proto1 != proto3
    assert proto3 != proto4
    assert proto1 is not None
    assert proto2 != str(proto2)


@pytest.mark.parametrize("names", [["ip4"], ["ip4", "tcp"], ["ip4", "tcp", "udp"]])
def test_protocols_with_string(names):
    expected = [protocols.protocol_with_name(name) for name in names]
    ins = "/".join(names)
    assert protocols.protocols_with_string(ins) == expected
    assert protocols.protocols_with_string("/" + ins) == expected
    assert protocols.protocols_with_string("/" + ins + "/") == expected


@pytest.mark.parametrize("invalid_name", ["", "/", "//"])
def test_protocols_with_string_invalid(invalid_name):
    assert protocols.protocols_with_string(invalid_name) == []


def test_protocols_with_string_mixed():
    names = ["ip4"]
    ins = "/".join(names)
    test_protocols_with_string(names)
    with pytest.raises(exceptions.StringParseError):
        names.append("foo")
        ins = "/".join(names)
        protocols.protocols_with_string(ins)


def test_add_protocol(valid_params):
    registry = protocols.ProtocolRegistry()
    proto = protocols.Protocol(**valid_params)
    registry.add(proto)
    assert proto.name in registry._names_to_protocols
    assert proto.code in registry._codes_to_protocols
    assert registry.find(proto.name) is registry.find(proto.code) is proto


def test_add_protocol_twice(valid_params):
    registry = protocols.ProtocolRegistry()
    proto = registry.add(protocols.Protocol(**valid_params))

    with pytest.raises(exceptions.ProtocolExistsError):
        registry.add(proto)
    del registry._names_to_protocols[proto.name]
    with pytest.raises(exceptions.ProtocolExistsError):
        registry.add(proto)
    del registry._codes_to_protocols[proto.code]
    registry.add(proto)


def test_add_protocol_alias():
    registry = protocols.REGISTRY.copy(unlock=True)
    tcp_proto = protocols.protocol_with_name("tcp")
    registry.add_alias_name("tcp", "abcd")
    registry.add_alias_code(tcp_proto, 123456)

    with pytest.raises(exceptions.ProtocolExistsError):
        registry.add_alias_name("tcp", "abcd")
    with pytest.raises(exceptions.ProtocolExistsError):
        registry.add_alias_code(tcp_proto, 123456)

    assert registry.find("tcp") is registry.find("abcd")
    assert registry.find("tcp") is registry.find(123456)


def test_add_protocol_lock(valid_params):
    registry = protocols.REGISTRY.copy(unlock=True)
    assert not registry.locked
    registry.lock()
    assert registry.locked

    with pytest.raises(exceptions.ProtocolRegistryLocked):
        registry.add(protocols.Protocol(**valid_params))
    with pytest.raises(exceptions.ProtocolRegistryLocked):
        registry.add_alias_name("tcp", "abcdef")
    with pytest.raises(exceptions.ProtocolRegistryLocked):
        tcp_proto = protocols.protocol_with_name("tcp")
        registry.add_alias_code(tcp_proto, 123456)


def test_protocol_repr():
    proto = protocols.protocol_with_name("ip4")
    assert "Protocol(code=4, name='ip4', codec='ip4')" == repr(proto)


def test_to_bytes_and_to_string_roundtrip():
    codec = memory.Codec()

    # some valid values
    for val in [0, 1, 42, 2**32, 2**64 - 1]:
        s = str(val)
        b = codec.to_bytes(None, s)
        # must be exactly 8 bytes
        assert isinstance(b, bytes)
        assert len(b) == 8
        # roundtrip back to string
        out = codec.to_string(None, b)
        assert out == s


def test_invalid_string_to_bytes():
    codec = memory.Codec()

    # not a number
    with pytest.raises(ValueError):
        codec.to_bytes(None, "abc")

    # negative number
    with pytest.raises(ValueError):
        codec.to_bytes(None, "-1")

    # too large
    with pytest.raises(ValueError):
        codec.to_bytes(None, str(2**64))


def test_invalid_bytes_to_string():
    codec = memory.Codec()

    # too short
    with pytest.raises(BinaryParseError):
        codec.to_string(None, b"\x00\x01")

    # too long
    with pytest.raises(BinaryParseError):
        codec.to_string(None, b"\x00" * 9)


def test_specific_encoding():
    codec = memory.Codec()

    # 42 encoded in big-endian
    expected_bytes = b"\x00\x00\x00\x00\x00\x00\x00*"
    assert codec.to_bytes(None, "42") == expected_bytes
    assert codec.to_string(None, expected_bytes) == "42"


def test_memory_validate_function():
    # Directly test the helper
    codec = memory.Codec()

    # Valid case
    codec.memory_validate(b"\x00" * 8)  # should not raise

    # Invalid length
    with pytest.raises(ValueError):
        codec.memory_validate(b"\x00" * 7)


def test_memory_integration_edge_values():
    # Minimum (0)
    ma0 = Multiaddr("/memory/0")
    assert str(ma0) == "/memory/0"
    assert ma0.value_for_protocol(777) == "0"

    # Maximum (2**64 - 1)
    max_val = str(2**64 - 1)
    mamax = Multiaddr(f"/memory/{max_val}")
    assert str(mamax) == f"/memory/{max_val}"
    assert mamax.value_for_protocol(777) == max_val


def test_memory_integration_invalid_values():
    # Negative number
    with pytest.raises(ValueError):
        Multiaddr("/memory/-1")

    # Too large (overflow > uint64)
    with pytest.raises(ValueError):
        Multiaddr(f"/memory/{2**64}")


def test_http_path_bytes_string_roundtrip():
    codec = http_path.Codec()

    # some valid HTTP path strings (URL-encoded input as expected by multiaddr system)
    from urllib.parse import quote

    for s in ["/foo", "/foo/bar", "/a b", "/こんにちは", "/path/with/special!@#"]:
        encoded_s = quote(s, safe="")  # Use same encoding as codec
        b = codec.to_bytes(None, encoded_s)
        assert isinstance(b, bytes)
        out = codec.to_string(None, b)
        # Should return the same URL-encoded string
        assert out == encoded_s


def test_http_path_empty_string_raises():
    codec = http_path.Codec()
    with pytest.raises(ValueError):
        codec.to_bytes(None, "")


def test_http_path_empty_bytes_raises():
    codec = http_path.Codec()
    with pytest.raises(BinaryParseError):
        codec.to_string(None, b"")


def test_http_path_special_characters():
    codec = http_path.Codec()
    path = "/foo bar/あいうえお"
    from urllib.parse import quote

    encoded_path = quote(path, safe="")  # Use same encoding as codec
    b = codec.to_bytes(None, encoded_path)

    assert codec.to_string(None, b) == encoded_path


def test_http_path_validate_function():
    codec = http_path.Codec()

    # valid path
    codec.validate(b"/valid/path")  # should not raise

    # empty path
    with pytest.raises(ValueError):
        codec.validate(b"")


def test_ipcidr_valid_roundtrip():
    codec = ipcidr.Codec()

    for val in ["0", "8", "16", "24", "32", "128", "255"]:
        b = codec.to_bytes(None, val)
        s = codec.to_string(None, b)

        # back and forth conversion should match
        assert s == val
        assert codec.to_bytes(None, s) == b


def test_ipcidr_bytes_to_string():
    codec = ipcidr.Codec()

    assert codec.to_string(None, bytes([0])) == "0"
    assert codec.to_string(None, bytes([24])) == "24"
    assert codec.to_string(None, bytes([255])) == "255"


def test_ipcidr_invalid_string_inputs():
    codec = ipcidr.Codec()

    with pytest.raises(StringParseError):
        codec.to_bytes(None, "-1")  # negative

    with pytest.raises(StringParseError):
        codec.to_bytes(None, "256")  # too large

    with pytest.raises(StringParseError):
        codec.to_bytes(None, "abc")  # not a number


def test_ipcidr_invalid_bytes_inputs():
    codec = ipcidr.Codec()

    with pytest.raises(BinaryParseError):
        codec.to_string(None, b"")  # empty

    with pytest.raises(BinaryParseError):
        codec.to_string(None, b"\x01\x02")  # too long

    with pytest.raises(ValueError):
        codec.validate(b"")  # validate should fail empty

    with pytest.raises(ValueError):
        codec.validate(b"\x01\x02")


# --------CERT-HASH---------

VALID_MULTIHASH_BYTES = multihash.encode(b"hello world", "sha2-256")
VALID_CERTHASH_STRING = multibase.encode("base64url", VALID_MULTIHASH_BYTES).decode("utf-8")

INVALID_BYTES = b"this is not a multihash"
INVALID_CONTENT_STRING = multibase.encode("base64url", INVALID_BYTES).decode("utf-8")


def test_certhash_valid_roundtrip():
    codec = certhash.Codec()
    b = codec.to_bytes(None, VALID_CERTHASH_STRING)
    assert isinstance(b, bytes)
    assert b == VALID_MULTIHASH_BYTES


def test_certhash_invalid_multihash_bytes_raises():
    """
    Tests that calling to_string() with bytes that are not a valid
    multihash raises a ValueError.
    """
    codec = certhash.Codec()
    with pytest.raises(ValueError):
        codec.to_string(None, INVALID_BYTES)


def test_certhash_valid_multibase_but_invalid_content_raises():
    """
    Tests that to_bytes() raises an error if the string is valid multibase
    but its decoded content is not a valid multihash.
    """
    codec = certhash.Codec()
    with pytest.raises(ValueError):
        codec.to_bytes(None, INVALID_CONTENT_STRING)


def test_certhash_invalid_multibase_string_raises():
    """
    Tests that passing a string with an invalid multibase prefix or
    encoding raises an error.
    """
    codec = certhash.Codec()
    # 'z' is a valid multibase prefix, but the content is not valid base58.
    invalid_string = "z-this-is-not-valid"
    with pytest.raises(Exception):  # Catches errors from the multibase library
        codec.to_bytes(None, invalid_string)


def test_certhash_memory_validate_function():
    """
    Directly tests the validate method.
    """
    codec = certhash.Codec()

    # A valid multihash should not raise an error
    codec.validate(VALID_MULTIHASH_BYTES)

    # Invalid bytes should raise a ValueError
    with pytest.raises(ValueError):
        codec.validate(INVALID_BYTES)
