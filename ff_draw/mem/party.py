import ctypes
import typing
import glm
import imgui

from nylib.utils.imgui import ctx as imgui_ctx
from nylib.utils.win32 import memory as ny_mem
from .actor import StatusManager
from .utils import direct_mem_property

if typing.TYPE_CHECKING:
    from . import XivMem


class MemberOffset:
    status = 0x0
    pos = 0x190
    character_id = 0x1a0
    id = 0x1a8
    current_hp = 0x1b4
    max_hp = 0x1b8
    current_mp = 0x1bc
    max_mp = 0x1be
    class_job = 0x205
    level = 0x206
    shield = 0x207

    size_ = 0X230


class MemberOffset650:
    status = 0x0
    pos = 0x2F0
    character_id = 0x300
    id = 0x308
    current_hp = 0x314
    max_hp = 0x318
    current_mp = 0x31C
    max_mp = 0x31E
    class_job = 0x365
    level = 0x366
    shield = 0x367

    size_ = 0X390


class Member:
    offsets = MemberOffset

    def __init__(self, handle, address):
        self.handle = handle
        self.address = address

    id = direct_mem_property(ctypes.c_uint)
    character_id = direct_mem_property(ctypes.c_uint64)
    current_hp = direct_mem_property(ctypes.c_uint)
    max_hp = direct_mem_property(ctypes.c_uint)
    current_mp = direct_mem_property(ctypes.c_ushort)
    max_mp = direct_mem_property(ctypes.c_ushort)
    class_job = direct_mem_property(ctypes.c_byte)
    level = direct_mem_property(ctypes.c_byte)
    shield = direct_mem_property(ctypes.c_ubyte)

    @property
    def pos(self):
        return glm.vec3.from_bytes(bytes(ny_mem.read_bytes(self.handle, self.address + self.offsets.pos, 0xc)))

    @property
    def status(self):
        return StatusManager(self.handle, self.address + self.offsets.status)

    @property
    def actor(self):
        # has bug, status manager in party is not the same as actor
        # return self.status.actor
        from . import XivMem
        return XivMem.instance.actor_table.get_actor_by_id(self.id)

    def render_debug(self):
        imgui.text(f'entity_id: {self.id:#x}')
        imgui.text(f'character_id: {self.character_id:#x}')
        imgui.text(f'hp: {self.current_hp}/{self.max_hp}')
        imgui.text(f'mp: {self.current_mp}/{self.max_mp}')
        imgui.text(f'job: {self.class_job}')
        imgui.text(f'level: {self.level}')
        imgui.text(f'shield: {self.shield}')
        pos = self.pos
        imgui.text(f'pos: {pos.x:.2f}, {pos.y:.2f}, {pos.z:.2f}')


class PartyOffset:
    members = 0
    party_size = 0x3d5c


class PartyOffset650(PartyOffset):
    members = 0X0
    party_size = 0X63DC


class Party:
    offsets = PartyOffset

    def __init__(self, handle, address):
        self.handle = handle
        self.address = address
        self.members = [Member(self.handle, self.address + self.offsets.members + i * Member.offsets.size_) for i in range(28)]

    def __iter__(self):
        for i in range(self.party_size):
            yield self.members[i]

    @property
    def party_size(self):
        return ny_mem.read_byte(self.handle, self.address + self.offsets.party_size)

    def render_debug(self):
        for i in range(self.party_size):
            with imgui_ctx.TreeNode(f'Member - {i}') as n, n:
                self.members[i].render_debug()


class PartyManager:
    def __init__(self, main: 'XivMem'):
        self.main = main
        real_party_address = main.scanner.find_point('48 ? ? * * * * 48 89 74 24 ? b2')[0]
        replay_party_address = real_party_address + main.scanner.find_val('74 ? f6 05 ? ? ? ? ? 48 ? ? * * * * 75')[0]
        if main.game_version >= (6, 5, 0):
            Party.offsets = PartyOffset650
            Member.offsets = MemberOffset650
        else:
            Party.offsets = PartyOffset
            Member.offsets = MemberOffset
        self.real_party = Party(self.main.handle, real_party_address)
        self.replay_party = Party(self.main.handle, replay_party_address)

    @property
    def party_list(self):
        return self.replay_party if self.main.is_in_replay else self.real_party

    def render_debug(self):
        self.party_list.render_debug()
