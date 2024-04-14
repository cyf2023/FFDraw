import ctypes.wintypes
import re
import typing

import glm

from nylib.utils.win32 import memory as ny_mem
from nylib.utils.win32.exception import WinAPIError

_addr_size = ctypes.sizeof(ctypes.c_void_p)
_T = typing.TypeVar('_T')
_T2 = typing.TypeVar('_T2')


def _setdefault(obj, key, default):
    if key in obj.__dict__:
        return obj.__dict__[key]
    setattr(obj, key, default)
    return default


def _iter_obj_properties(owner, k):
    yield_names = set()
    for k, v in (cls_.__dict__[k].items() for cls_ in owner.__mro__ if k in cls_.__dict__):
        if k in yield_names: continue
        yield_names.add(k)
        yield k, v


class bit_field_property:
    k = '__bit_field_property__'

    def __init__(self, offset, size=1):
        self.byte_off = offset // 8
        self.bit_off = offset % 8
        self.mask = (1 << size) - 1
        self.data_size = (self.bit_off + size + 7) // 8 * 8

    @classmethod
    def obj_properties(cls, owner):
        yield from _iter_obj_properties(owner, cls.k)

    def __set_name__(self, owner, name):
        _setdefault(owner, self.k, {})[name] = self

    def get_instance_value(self, instance):
        return getattr(ny_mem, 'read_uint' + str(self.data_size))(instance.handle, instance.address + self.byte_off)

    def __get__(self, instance, owner):
        return (self.get_instance_value(instance) >> self.bit_off) & self.mask

    def set_instance_value(self, instance, value):
        getattr(ny_mem, 'write_uint' + str(self.data_size))(instance.handle, instance.address + self.byte_off, value)

    def __set__(self, instance, value):
        new_val = (self.get_instance_value(instance) & ~(self.mask << self.bit_off)) | ((value & self.mask) << self.bit_off)
        self.set_instance_value(instance, new_val)


def glm_mem_property(_type: typing.Type[_T], offset_key=None, default=0) -> _T | None: ...  # dirty type hinting


class glm_mem_property(typing.Generic[_T]):
    k = '__glm_mem_property__'

    def __init__(self, t: typing.Type[_T], offset_key=None, default=0, is_static=False):
        self.t = t
        self.size = glm.sizeof(t)
        self.offset_key = offset_key
        self.default = default
        self.is_static = is_static
        self.name = None
        self.owner = None

    @classmethod
    def obj_properties(cls, owner):
        yield from _iter_obj_properties(owner, cls.k)

    def __set_name__(self, owner, name):
        self.name = name
        self.owner = owner
        if not self.offset_key: self.offset_key = name
        _setdefault(owner, self.k, {})[name] = self

    def __get__(self, instance, owner) -> _T:
        addr = 0
        if not self.is_static and not (addr := instance.address):
            return self.default
        return self.t.from_bytes(bytes(ny_mem.read_bytes(instance.handle, addr + getattr(self.owner.offsets, self.offset_key), self.size)))

    def __set__(self, instance, value: _T):
        addr = 0
        if not self.is_static and not (addr := instance.address): return
        return ny_mem.write_bytes(instance.handle, addr + getattr(self.owner.offsets, self.offset_key), value.to_bytes())


class direct_mem_property:
    k = '__direct_mem_property__'

    def __init__(self, _type, offset_key=None, default=0, is_static=False):
        self.type = _type
        self.offset_key = offset_key
        self.default = default
        self.is_static = is_static
        self.name = None
        self.owner = None

    @classmethod
    def obj_properties(cls, owner):
        yield from _iter_obj_properties(owner, cls.k)

    def __set_name__(self, owner, name):
        self.name = name
        self.owner = owner
        if not self.offset_key: self.offset_key = name
        _setdefault(owner, self.k, {})[name] = self

    def __get__(self, instance, owner) -> 'float | int | direct_mem_property':
        if instance is None: return self
        addr = 0
        if not self.is_static and not (addr := instance.address): return self.default
        try:
            return ny_mem.read_memory(
                instance.handle, self.type,
                addr + getattr(self.owner.offsets, self.offset_key)).value
        except WinAPIError:
            return self.default

    def __set__(self, instance, value):
        if instance is None: return
        addr = 0
        if not self.is_static and not (addr := instance.address): return
        try:
            return ny_mem.write_bytes(instance.handle, addr + getattr(self.owner.offsets, self.offset_key), bytearray(self.type(value)))
        except Exception:
            return


def struct_mem_property(_type: typing.Type[_T], is_pointer=False, pass_self=False, offset_key=None) -> _T | None: ...  # dirty type hinting


class struct_mem_property(typing.Generic[_T]):
    k = '__struct_mem_property__'
    cache_k = '__struct_mem_property_cache__'

    def __init__(self, _type: typing.Type[_T], is_pointer=False, pass_self: bool | str = False, offset_key=None, is_static=False):
        self.type = _type
        self.is_pointer = is_pointer
        self.pass_self = pass_self
        self.offset_key = offset_key
        self.is_static = is_static
        self.name = None
        self.owner = None

    @classmethod
    def obj_properties(cls, owner):
        yield from _iter_obj_properties(owner, cls.k)

    def __set_name__(self, owner, name):
        self.owner = owner
        self.name = name
        if not self.offset_key: self.offset_key = name
        _setdefault(owner, self.k, {})[name] = self

    def __get__(self, instance, owner) -> _T | None:
        if instance is None: return self
        cache = getattr(instance, self.cache_k, {})
        if self.name in cache: return cache[self.name]
        addr = 0
        if not self.is_static and not (addr := instance.address): return None
        addr += getattr(self.owner.offsets, self.offset_key)
        if self.is_pointer and not (addr := ny_mem.read_address(instance.handle, addr)):
            return None
        a1 = getattr(instance, self.pass_self) if isinstance(self.pass_self, str) else instance if self.pass_self else instance.handle
        res = self.type(a1, addr)
        if not self.is_pointer:
            cache[self.name] = res
            setattr(instance, self.cache_k, cache)
        return res

    def __set__(self, instance, value):
        if instance is None: return
        addr = 0
        if not self.is_static and not (addr := instance.address): return
        addr += getattr(self.owner.offsets, self.offset_key)
        if self.is_pointer:
            ny_mem.write_address(instance.handle, addr, value.address)
        else:
            raise TypeError('cannot set value to a non-pointer struct')
            # ny_mem.write_bytes(instance.handle, addr, value)


def get_hwnd(pid):
    _p_hwnds = []

    def _filter_func(hwnd, param):
        rtn_value = ctypes.wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(rtn_value))
        if rtn_value.value == pid:
            str_buffer = (ctypes.c_char * 512)()
            ctypes.windll.user32.GetClassNameA(hwnd, str_buffer, 512)
            if str_buffer.value == b'FFXIVGAME': _p_hwnds.append(hwnd)
            return False
        return True

    _c_filter_func = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)(_filter_func)
    ctypes.windll.user32.EnumWindows(_c_filter_func, 0)
    if _p_hwnds:
        return _p_hwnds[0]
    else:
        raise ValueError('no hwnd found')


def get_game_version_info(file_name):
    with open(file_name, 'rb') as f: base_data = f.read()
    match = re.search(r"/\*{5}ff14\*{6}rev\d+_(\d{4})/(\d{2})/(\d{2})".encode(), base_data)
    game_build_date: str = f"{match.group(1).decode()}.{match.group(2).decode()}.{match.group(3).decode()}.0000.0000"
    match = re.search(r'(\d{3})\\trunk\\prog\\client\\Build\\FFXIVGame\\x64-Release\\ffxiv_dx11.pdb'.encode(), base_data)
    game_version: tuple[int, int, int] = tuple(b - 48 for b in match.group(1))
    return game_version, game_build_date


def read_utf8_string(handle, d: int, encoding='utf-8'):
    return ny_mem.read_string(handle, ny_mem.read_address(handle, d), ny_mem.read_ulonglong(handle, d + 0x10), encoding)


class StdVector(typing.Generic[_T]):
    def __init__(self, handle, address, d_type: typing.Type[_T], d_size):
        self.handle = handle
        self.address = address
        self.d_type = d_type
        self.d_size = d_size

    @property
    def p_start(self):
        return ny_mem.read_address(self.handle, self.address)

    @property
    def p_end(self):
        return ny_mem.read_address(self.handle, self.address + _addr_size)

    def __len__(self):
        return (self.p_end - self.p_start) // self.d_size

    def __getitem__(self, index) -> _T:
        return self.d_type(self.handle, self.p_start + index * self.d_size)

    def __iter__(self) -> typing.Iterator[_T]:
        first = self.p_start
        last = self.p_end
        for i in range((last - first) // self.d_size):
            yield self.d_type(self.handle, first + i * self.d_size)


class _SimpleArr(typing.Generic[_T]):
    _item_count_: int
    _item_size_: int
    _reader_: typing.Callable[[typing.Any, int], _T]
    _writer_: typing.Callable[[typing.Any, int, _T], None]

    def __init__(self, handle, address):
        self.handle = handle
        self.address = address

    def __len__(self):
        return self._item_count_

    @typing.overload
    def __getitem__(self, idx: int) -> _T:
        ...

    @typing.overload
    def __getitem__(self, idx: slice) -> typing.Generator[_T, None, None]:
        ...

    def _simp_slice_(self, key):
        start = key.start or 0
        if start < 0: start += self._item_count_
        stop = key.stop or self._item_count_
        if stop < 0: stop += self._item_count_
        return start, stop

    def __getitem__(self, idx):
        assert (address := self.address), "Null pointer"
        if isinstance(idx, int):
            return self._reader_(self.handle, address + idx * self._item_size_)
        elif isinstance(idx, slice):
            start, stop = self._simp_slice_(idx)
            return tuple(self._reader_(self.handle, address + i * self._item_size_) for i in range(start, stop))
        else:
            raise TypeError(f"Invalid index type: {type(idx)}")

    def __setitem__(self, key, value):
        assert (address := self.address), "Null pointer"
        if isinstance(key, int):
            self._writer_(self.handle, address + key * self._item_size_, value)
        elif isinstance(key, slice):
            start, stop = self._simp_slice_(key)
            for i, item in zip(range(start, stop), value):
                self._writer_(self.handle, address + i * self._item_size_, item)

    def __iter__(self) -> typing.Generator[_T, None, None]:
        assert (address := self.address), "Null pointer"
        if hasattr(self, '_item_count_'):
            for i in range(self._item_count_):
                yield self._reader_(self.handle, address + i * self._item_size_)
        else:
            while True:
                yield self._reader_(self.handle, address)
                address += self._item_size_

    def __class_getitem__(cls: typing.Type[_T2], item_count: int) -> typing.Type[_T2]:
        assert (dims := getattr(cls, "_arr_dims_", 0)) < 1, "SimpleArr cannot be nested"
        return type(f'{cls.__name__}[{item_count}]', (cls,), {
            '_item_count_': item_count,
            '_arr_dims_': dims + 1
        })


def _simple_arr_factory(t_name, reader, writer, item_size, hint_type: typing.Type[_T]) -> 'type[_SimpleArr[_T]]':
    return type(f'Arr<{t_name}>', (_SimpleArr,), {'_item_size_': item_size, '_reader_': staticmethod(reader), '_writer_': staticmethod(writer)})


class _SimplePtr(_SimpleArr[_T]):
    def __init__(self, handle, address):
        self.handle = handle
        self.p_address = address

    @property
    def address(self):
        assert (p_address := self.p_address), "Null pointer"
        return ny_mem.read_address(self.handle, p_address)

    @address.setter
    def address(self, value):
        assert (p_address := self.p_address), "Null pointer"
        ny_mem.write_address(self.handle, p_address, value)

    @property
    def content(self) -> _T:
        return self[0]

    @content.setter
    def content(self, value):
        self[0] = value


def _simple_ptr_factory(t_name, reader, writer, item_size, hint_type: typing.Type[_T]) -> 'type[_SimplePtr[_T]]':
    return type(f'Ptr<{t_name}>', (_SimplePtr,), {'_item_size_': item_size, '_reader_': staticmethod(reader), '_writer_': staticmethod(writer)})


int8_arr = _simple_arr_factory('int8', ny_mem.read_int8, ny_mem.write_int8, 1, int)
int16_arr = _simple_arr_factory('int16', ny_mem.read_int16, ny_mem.write_int16, 2, int)
int32_arr = _simple_arr_factory('int32', ny_mem.read_int32, ny_mem.write_int32, 4, int)
int64_arr = _simple_arr_factory('int64', ny_mem.read_int64, ny_mem.write_int64, 8, int)
uint8_arr = _simple_arr_factory('uint8', ny_mem.read_uint8, ny_mem.write_uint8, 1, int)
uint16_arr = _simple_arr_factory('uint16', ny_mem.read_uint16, ny_mem.write_uint16, 2, int)
uint32_arr = _simple_arr_factory('uint32', ny_mem.read_uint32, ny_mem.write_uint32, 4, int)
uint64_arr = _simple_arr_factory('uint64', ny_mem.read_uint64, ny_mem.write_uint64, 8, int)
float_arr = _simple_arr_factory('float', ny_mem.read_float, ny_mem.write_float, 4, float)
ptr_arr = _simple_arr_factory('ptr', ny_mem.read_address, ny_mem.write_address, ctypes.sizeof(ctypes.c_void_p), int)

int8_ptr = _simple_ptr_factory('int8', ny_mem.read_int8, ny_mem.write_int8, 1, int)
int16_ptr = _simple_ptr_factory('int16', ny_mem.read_int16, ny_mem.write_int16, 2, int)
int32_ptr = _simple_ptr_factory('int32', ny_mem.read_int32, ny_mem.write_int32, 4, int)
int64_ptr = _simple_ptr_factory('int64', ny_mem.read_int64, ny_mem.write_int64, 8, int)
uint8_ptr = _simple_ptr_factory('uint8', ny_mem.read_uint8, ny_mem.write_uint8, 1, int)
uint16_ptr = _simple_ptr_factory('uint16', ny_mem.read_uint16, ny_mem.write_uint16, 2, int)
uint32_ptr = _simple_ptr_factory('uint32', ny_mem.read_uint32, ny_mem.write_uint32, 4, int)
uint64_ptr = _simple_ptr_factory('uint64', ny_mem.read_uint64, ny_mem.write_uint64, 8, int)
float_ptr = _simple_ptr_factory('float', ny_mem.read_float, ny_mem.write_float, 4, float)
ptr_ptr = _simple_ptr_factory('ptr', ny_mem.read_address, ny_mem.write_address, ctypes.sizeof(ctypes.c_void_p), int)
