import typing

import glm

from ff_draw.omen import Line
from ff_draw.omen.effector import Effector
from nylib.utils import safe_lazy, safe
from .logic import *
from .trigger import new_thread
from .typing import *

main = FFDraw.instance
raid_helper: 'RaidHelper|None' = None
circle_shape = lambda: 0x10000
rect_shape = lambda t=0: 0x20000 | t
fan_shape = lambda degree: 0x50000 | degree
donut_shape = lambda inner, outer: 0x10000 | int(inner / outer * 0xffff)
is_shape_circle = lambda shape: shape >> 16 == 1
is_shape_rect = lambda shape: shape >> 16 == 2
is_shape_fan = lambda shape: shape >> 16 == 5


class TimeGradientEffector(Effector):
    start = glm.vec3(1, 1, 0)  # color: yellow
    percent = 0

    def update(self):
        if self.omen.duration <= 0: return False
        self.percent = 1 - (self.omen.remaining_time - 1) / self.omen.duration
        if self.percent >= 1: return False
        return True

    def color(self, c: glm.vec4):
        return glm.vec4(*(
            glm.mix(self.start[i], c[i], self.percent)
            for i in range(3)
        ), c.w)


def default_color(is_enemy=True):
    """
    返回敌友字符串
    """
    if is_enemy:
        if raid_helper.game_style:
            return 'g_enemy'
        else:
            return 'enemy'
    else:
        if raid_helper.game_style:
            return 'g_friend'
        else:
            return 'friend'


def pos_tracker(actor: Actor):
    """
    返回一个单位的坐标
    @return: x,z,y
    """
    if not isinstance(actor, NActor): actor = NActor(actor)
    return lambda o: safe_lazy(lambda: actor.update().pos, _default=o.timeout)


def facing_tracker(actor: Actor):
    if not isinstance(actor, NActor): actor = NActor(actor)
    return lambda o: safe_lazy(lambda: actor.update().facing, _default=o.timeout)


class OmenGroup:
    def __init__(self, *omens: BaseOmen):
        self.omens = list(omens)

    def append(self, omen: BaseOmen):
        self.omens.append(omen)

    def __iter__(self):
        return iter(self.omens)

    def __getitem__(self, item):
        return self.omens[item]

    def timeout(self):
        for o in self.omens:
            o.timeout()

    def destroy(self):
        for o in self.omens:
            o.destroy()

    def __setattr__(self, key, value):
        if key in ('omens',):
            return super().__setattr__(key, value)
        for o in self.omens:
            setattr(o, key, value)

    def __add__(self, other):
        assert isinstance(other, OmenGroup)
        return OmenGroup(*self.omens, *other.omens)

    def __iadd__(self, other):
        assert isinstance(other, OmenGroup)
        self.omens.extend(other.omens)
        return self


def draw_distance_line(
        pos1: typing.Callable[[], glm.vec3] | glm.vec3 | Actor,
        pos2: typing.Callable[[], glm.vec3] | glm.vec3 | Actor,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        duration: float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
        min_distance: float = None,
        max_distance: float = None,
        step_distance: float = 1,
):
    if isinstance(pos1, Actor): pos1 = pos_tracker(pos1)
    if isinstance(pos2, Actor): pos2 = pos_tracker(pos2)
    scale = glm.scale(glm.vec3(step_distance * .5, 1, step_distance * .5))

    def draw_arrow_line(start: glm.vec3, end: glm.vec3, _surface_color: glm.vec4, _line_color: glm.vec4, offset=0.):
        norm_d = glm.normalize(end - start)
        dis = glm.distance(start, end)
        rot = glm.polar(norm_d).y
        drawn = offset * step_distance
        while drawn < dis:
            main.gui.add_3d_shape(
                shape=0x1010000,
                transform=glm.translate(start + (norm_d * drawn)) * glm.rotate(rot, glm.vec3(0, 1, 0)) * scale,
                surface_color=_surface_color,
                line_color=_line_color,
            )
            drawn += step_distance

    def draw_dot_line(start: glm.vec3, end: glm.vec3, _line_color: glm.vec4):
        norm_d = glm.normalize(end - start)
        dis = glm.distance(start, end)
        drawn = 0
        while drawn < dis:
            main.gui.add_3d_shape(shape=0x90000, transform=glm.translate(start + (norm_d * drawn)), point_color=_line_color)
            drawn += step_distance

    def get_shape(o: BaseOmen):
        _pos1 = o.get_maybe_callable(pos1) + glm.vec3(0, .5, 0)
        _pos2 = o.get_maybe_callable(pos2) + glm.vec3(0, .5, 0)
        if _pos1 is None or _pos2 is None: return 0
        xz_dis = glm.distance(_pos1.xz, _pos2.xz)
        mid = (_pos1 + _pos2) / 2
        offset = (o.play_time % .5) / .5
        if surface_color is None and line_color is None and color is None:
            _surface_color, _line_color = map(o.get_color, o.preset_colors.get(default_color(
                min_distance is not None and xz_dis < min_distance or max_distance is not None and xz_dis > max_distance
            )))
        elif color is None:
            _surface_color = o.get_maybe_callable(surface_color)
            _line_color = o.get_maybe_callable(line_color)
            _surface_color = o.get_color(o.preset_colors.get(_surface_color)[0] if _surface_color in o.preset_colors else _surface_color)
            _line_color = o.get_color(o.preset_colors.get(_line_color)[1] if _line_color in o.preset_colors else _line_color)
        else:
            _color = o.get_maybe_callable(color)
            _surface_color, _line_color = map(o.get_color, o.preset_colors.get(_color) if isinstance(_color, str) else (_color, None))

        if min_distance is not None and xz_dis < min_distance:
            draw_arrow_line(mid, _pos1, _surface_color, _line_color, offset)
            draw_arrow_line(mid, _pos2, _surface_color, _line_color, offset)
        elif max_distance is not None and xz_dis > max_distance:
            draw_arrow_line(_pos1, mid, _surface_color, _line_color, offset)
            draw_arrow_line(_pos2, mid, _surface_color, _line_color, offset)
        else:
            draw_dot_line(mid, _pos1, _line_color)
            draw_dot_line(mid, _pos2, _line_color)
        return 0

    return create_game_omen(shape=get_shape, pos=glm.vec3(), scale=glm.vec3(), duration=duration, alpha=alpha)


def draw_knock_predict_circle(
        radius: typing.Callable[[], float] | float,
        pos: typing.Callable[[], glm.vec3] | glm.vec3 | Actor,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        duration: float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
        actor: Actor = None,
        knock_distance: int = True,
):
    def _pos_tracker(actor: Actor):
        if not isinstance(actor, NActor): actor = NActor(actor)
        return lambda: safe(lambda: actor.update().pos, _default=None)

    def _maybe_callable(v):
        return v() if callable(v) else v

    if isinstance(pos, Actor): pos = _pos_tracker(pos)
    if actor is None: actor = get_me()
    a_pos = _pos_tracker(actor)

    def check_hit():
        _apos = a_pos()
        _pos = _maybe_callable(pos)
        if _apos is None or _pos is None: return None
        if glm.distance(_apos, _pos) < _maybe_callable(radius):
            return glm.polar(_pos - _apos).y

    def play(dis):
        def get_shape(o: BaseOmen):
            if (knock_direction := check_hit()) is None: return 0
            o._pos = a_pos() + glm.vec3(-math.sin(knock_direction) * dis, 0, -math.cos(knock_direction) * dis)
            o._facing = knock_direction + math.pi
            return 0x1010000

        return create_game_omen(
            pos=glm.vec3(),
            shape=get_shape,
            facing=0,
            scale=glm.vec3(.5, 1, .5),
            surface_color=surface_color, line_color=line_color, color=color,
            duration=duration,
            alpha=alpha,
        )

    def play_end(dis):
        def get_shape(o: BaseOmen):
            if (knock_direction := check_hit()) is None: return 0
            o._pos = a_pos() + glm.vec3(-math.sin(knock_direction) * dis, 0, -math.cos(knock_direction) * dis)
            return 0x10000

        return create_game_omen(
            pos=glm.vec3(),
            shape=get_shape,
            facing=0,
            scale=glm.vec3(.5, 1, .5),
            surface_color=surface_color, line_color=line_color, color=color,
            duration=duration,
            alpha=alpha,
        )

    knock_distance = _maybe_callable(knock_distance)
    return OmenGroup(
        play_end(knock_distance),
        *(play(dis) for dis in range(knock_distance))
    )


def draw_decay(
        radius: typing.Callable[[BaseOmen], float] | float,
        pos: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3 | Actor,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        label: typing.Callable[[BaseOmen], str] | str = '',
        label_color: typing.Callable[[BaseOmen], tuple[float, float, float,]] | tuple[float, float, float,] = None,
        duration: float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
        min_radius: typing.Callable[[BaseOmen], float] | float = None,
        draw_icon: typing.Callable[[BaseOmen], bool] | bool = True,
):
    if isinstance(pos, Actor):
        pos = pos_tracker(pos)

    def play(f):
        def get_shape(o: BaseOmen):
            _pos = o.get_maybe_callable(pos)
            if not _pos: return 0
            dis = (o.play_time % 1) * 1 + 4
            o._pos = _pos + glm.vec3(-math.sin(f) * dis, 2, -math.cos(f) * dis)
            o._facing = f + math.pi
            return 0x1010000

        return create_game_omen(
            pos=pos,
            shape=get_shape,
            facing=0,
            scale=glm.vec3(3, 1, 2),
            surface_color=surface_color, line_color=line_color, color=color,
            duration=duration,
            alpha=alpha,
        )

    omens = [
        draw_circle(  # 扩散圈
            radius=lambda o: (o.play_time % 1) * (o.get_maybe_callable(radius) - 1) + 1, pos=pos,
            color=color,
            line_color=color or line_color or default_color(True),
            label=label, label_color=label_color,
            duration=duration, alpha=alpha
        ),
    ]
    if min_radius is not None:
        omens.append(draw_circle(  # 最小圈
            radius=min_radius, pos=pos,
            color=color,
            surface_color=surface_color,
            line_color=line_color,
            label=label, label_color=label_color,
            duration=duration, alpha=alpha
        ))
    if draw_icon:
        omens.append(
            draw_circle(  # 内圈
                radius=1, pos=lambda o: o.get_maybe_callable(pos) + glm.vec3(0, 2, 0),
                color=color,
                surface_color=surface_color,
                line_color=line_color,
                label=label, label_color=label_color,
                duration=duration, alpha=alpha
            ))
        for i in range(3):
            omens.append(play(i * math.pi * 2 / 3))
    return OmenGroup(*omens)


def draw_share(
        radius: typing.Callable[[BaseOmen], float] | float,
        pos: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3 | Actor,
        facing: typing.Callable[[BaseOmen], float] | float | Actor = 0,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        label: typing.Callable[[BaseOmen], str] | str = '',
        label_color: typing.Callable[[BaseOmen], tuple[float, float, float,]] | tuple[float, float, float,] = None,
        duration: float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
):
    if isinstance(pos, Actor):
        pos = pos_tracker(pos)
    if isinstance(facing, Actor):
        facing = facing_tracker(facing)

    def play(f):
        def get_shape(o: BaseOmen):
            if not (_radius := o.get_maybe_callable(radius)): return 0
            fac = (o.get_maybe_callable(facing) or 0) + f
            if not (_pos := o.get_maybe_callable(pos)): return 0
            dis = _radius * ((1 - (time.time() - o.start_at) % 1) * .4 + .8)
            o._pos = _pos + glm.vec3(math.cos(fac) * dis, 2, -math.sin(fac) * dis)
            o._facing = fac - math.pi / 2
            o._scale = glm.vec3(_radius / 5, 1, _radius / 5)
            return 0x1010000

        return create_game_omen(
            pos=pos,
            shape=get_shape,
            facing=facing,
            scale=glm.vec3(1, 1, 1),
            surface_color=surface_color, line_color=line_color, color=color,
            duration=duration,
            alpha=alpha,
        )

    return OmenGroup(
        draw_circle(
            radius=radius, pos=lambda o: o.get_maybe_callable(pos) + glm.vec3(0, 2, 0),
            line_color=color or line_color or default_color(True),
            label=label, label_color=label_color,
            duration=duration, alpha=alpha
        ),
        *(play(i * math.pi / 2) for i in range(4))
    )


def draw_circle(
        radius: typing.Callable[[BaseOmen], float] | float,
        pos: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3 | Actor,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        label: typing.Callable[[BaseOmen], str] | str = '',
        label_color: typing.Callable[[BaseOmen], tuple[float, float, float,]] | tuple[float, float, float,] = None,
        duration: float = 0,
        inner_radius: typing.Callable[[BaseOmen], float] | float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
):
    if isinstance(radius, int):
        scale = glm.vec3(radius, 1, radius)
    else:
        def scale(o: BaseOmen):
            r = o.get_maybe_callable(radius)
            return glm.vec3(r, 1, r)
    if isinstance(radius, int) and isinstance(inner_radius, int):
        shape = 0x10000 | int(inner_radius / radius * 0xffff)
    else:
        def shape(o: BaseOmen):
            return 0x10000 | int(o.get_maybe_callable(inner_radius) / o.get_maybe_callable(radius) * 0xffff)

    return create_game_omen(
        pos=pos,
        shape=shape,
        scale=scale,
        surface_color=surface_color, line_color=line_color, color=color,
        label=label, label_color=label_color,
        duration=duration,
        alpha=alpha,
    )


def draw_rect(
        width: typing.Callable[[BaseOmen], float] | float,
        length: typing.Callable[[BaseOmen], float] | float,
        pos: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3 | Actor,
        facing: typing.Callable[[BaseOmen], float] | float | Actor = None,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        label: typing.Callable[[BaseOmen], str] | str = '',
        label_color: typing.Callable[[BaseOmen], tuple[float, float, float,]] | tuple[float, float, float,] = None,
        duration: float = 0,
        arg=0,  # 0:normal, 1:include back, 2:cross
        alpha: typing.Callable[[BaseOmen], float] | float = None,
):
    if isinstance(width, int) and isinstance(length, int):
        scale = glm.vec3(width, 1, length)
    else:
        def scale(o: BaseOmen):
            return glm.vec3(o.get_maybe_callable(width), 1, o.get_maybe_callable(length))
    return create_game_omen(
        pos=pos,
        shape=0x20000 | arg,
        scale=scale,
        facing=facing,
        surface_color=surface_color, line_color=line_color, color=color,
        label=label, label_color=label_color,
        duration=duration,
        alpha=alpha,
    )


def draw_fan(
        degree: typing.Callable[[BaseOmen], float] | float,
        radius: typing.Callable[[BaseOmen], float] | float,
        pos: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3 | Actor,
        facing: typing.Callable[[BaseOmen], float] | float | Actor = None,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        label: typing.Callable[[BaseOmen], str] | str = '',
        label_color: typing.Callable[[BaseOmen], tuple[float, float, float,]] | tuple[float, float, float,] = None,
        duration: float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
):
    if isinstance(radius, int):
        scale = glm.vec3(radius, 1, radius)
    else:
        def scale(o: BaseOmen):
            r = o.get_maybe_callable(radius)
            return glm.vec3(r, 1, r)

    if isinstance(degree, int):
        shape = 0x50000 | degree
    else:
        def shape(o: BaseOmen):
            return 0x50000 | o.get_maybe_callable(degree)

    return create_game_omen(
        pos=pos,
        shape=shape,
        scale=scale,
        facing=facing,
        surface_color=surface_color, line_color=line_color, color=color,
        label=label, label_color=label_color,
        duration=duration,
        alpha=alpha,
    )


def linear_trans(start_s, start_p, end_s, end_p, remain):
    return max(min((start_s - remain) / (start_s - end_s), 1), 0) * (end_p - start_p) + start_p


def create_game_omen(
        shape: typing.Callable[[BaseOmen], float] | float,
        scale: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3,
        pos: typing.Callable[[BaseOmen], glm.vec3] | glm.vec3 | Actor,
        facing: typing.Callable[[BaseOmen], float] | float | Actor = None,
        color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        surface_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        line_color: typing.Callable[[BaseOmen], glm.vec4 | str] | glm.vec4 | str = None,
        label: typing.Callable[[BaseOmen], str] | str = '',
        label_color: typing.Callable[[BaseOmen], tuple[float, float, float,]] | tuple[float, float, float,] = None,
        duration: float = 0,
        alpha: typing.Callable[[BaseOmen], float] | float = None,
):
    if surface_color is None and line_color is None and color is None:
        color = default_color(True)
    if isinstance(pos, Actor):
        if facing is None:
            facing = facing_tracker(pos)
        pos = pos_tracker(pos)
    elif facing is None:
        facing = 0
    omen = BaseOmen(
        main=main,
        pos=pos,
        shape=shape,
        scale=scale,
        facing=facing,
        surface_color=surface_color, line_color=line_color, surface_line_color=color,
        label=label, label_color=label_color,
        duration=duration,
        alpha=alpha
    )
    if raid_helper.enemy_gradient and color in ('enemy', 'g_enemy'):
        omen.apply_effect(TimeGradientEffector)
    return omen


def draw_line(
        source: Actor | glm.vec3 | typing.Callable[[BaseOmen], glm.vec3],
        target: Actor | glm.vec3 | typing.Callable[[BaseOmen], glm.vec3],
        color: glm.vec4,
        width: int = 3,
        duration=0
):
    if isinstance(source, Actor):
        source = pos_tracker(source)
    if isinstance(target, Actor):
        target = pos_tracker(target)
    return Line(
        main=main,
        src=source,
        dst=target,
        line_color=color,
        line_width=width,
        duration=duration
    )


def timeout_when_cancel(omen: BaseOmen, actor: Actor | int):
    if isinstance(actor, Actor): actor = actor.id

    on_net_msg = lambda m: remove(m.header.source_id)
    on_ac_msg = lambda m: remove(m.source_id)

    def remove(check_id=None):
        if check_id is not None and check_id != actor: return
        main.sniffer.on_action_effect.remove(on_net_msg)
        main.sniffer.on_zone_server_message[ZoneServer.ActorCast].remove(on_net_msg)
        main.sniffer.on_actor_control[ActorControlId.CancelCast].remove(on_ac_msg)
        omen.timeout()

    @new_thread
    def install():
        with main.sniffer.ipc_lock:
            main.sniffer.on_action_effect.append(on_net_msg)
            main.sniffer.on_zone_server_message[ZoneServer.ActorCast].append(on_net_msg)
            main.sniffer.on_actor_control[ActorControlId.CancelCast].append(on_ac_msg)

            old_shape = omen._shape
            omen._shape = lambda o: o.get_maybe_callable(old_shape) if main.mem.actor_table.get_actor_by_id(actor) else o.timeout()
            old_destroy = omen.destroy
            omen.destroy = lambda: (remove(), old_destroy())

    install()
    return omen


def timeout_when_channeling_change(omen: BaseOmen, source_id, target_id=None, idx=0):
    if isinstance(source_id, ActorControlMessage):
        source_id, target_id, idx = source_id.source_id, source_id.param.target_id, source_id.param.idx
    else:
        assert target_id is not None, 'target_id must be specified if source_id is not ActorControlMessage'

    def on_channeling(msg: ActorControlMessage[actor_control.SetChanneling | actor_control.RemoveChanneling]):
        print('on_channeling', msg.id, msg.source_id, msg.param.idx)
        if msg.source_id == source_id and msg.param.idx == idx: remove()

    def remove():
        main.sniffer.on_actor_control[ActorControlId.SetChanneling].remove(on_channeling)
        main.sniffer.on_actor_control[ActorControlId.RemoveChanneling].remove(on_channeling)
        omen.timeout()

    get_actor_by_id = main.mem.actor_table.get_actor_by_id

    def validate_shape():
        return (src_actor := get_actor_by_id(source_id)) and (c := src_actor.get_channeling(idx)) and c.target_id == target_id

    @new_thread
    def install():
        with main.sniffer.ipc_lock:
            print('install', source_id, idx)
            main.sniffer.on_actor_control[ActorControlId.SetChanneling].append(on_channeling)
            main.sniffer.on_actor_control[ActorControlId.RemoveChanneling].append(on_channeling)

            old_shape = omen._shape
            omen._shape = lambda o: o.get_maybe_callable(old_shape) if validate_shape() else o.timeout()
            old_destroy = omen.destroy
            omen.destroy = lambda: (remove(), old_destroy())

    install()
    return omen


class Waypoint:
    REACH_DIS = 1
    POP_WHEN_REACH = 0
    POP_MANUAL = 1

    def __init__(self, l: 'WaypointList', pos: glm.vec3, pop_mode=POP_WHEN_REACH, reach_dis=REACH_DIS, auto_pop=-1., surface_color: glm.vec3 = None, line_color: glm.vec3 = None):
        self.l = l
        self._pos = pos
        self.pop_mode = pop_mode
        self.reach_dis = reach_dis
        self.auto_pop = auto_pop
        self.surface_color = surface_color
        self.line_color = line_color
        if auto_pop > 0:
            self.pop_at = time.time() + auto_pop
            new_thread(self._delay_pop)()
        else:
            self.pop_at = 1e+99

    @property
    def pos(self):
        return self._pos(self) if callable(self._pos) else self._pos

    def _delay_pop(self):
        if self.auto_pop > 0:
            time.sleep(self.auto_pop)
            self.pop()

    @property
    def is_valid(self):
        return self in self.l

    def pop(self):
        try:
            self.l.remove(self)
        except ValueError:
            return False
        return True

    @property
    def idx(self):
        return self.l.index(self)

    def is_reach(self, pos: glm.vec3):
        pos_ = self.pos
        if pos_ is None: return True
        return glm.distance(pos, pos_) < self.reach_dis

    def should_pop(self, me_pos):
        if self.pop_mode != self.POP_WHEN_REACH: return False
        return self.is_reach(me_pos)

    def __repr__(self):
        return f'<Waypoint {self.pos}>'


def color_gradient(timestamp):
    # 设置渐变周期为1秒
    period = 1
    # 计算归一化时间
    t = timestamp % period / period
    # 计算红色分量
    red = (math.sin(2 * math.pi * t) + 1) / 2
    # 计算绿色分量
    green = (math.sin(2 * math.pi * (t + 1 / 3)) + 1) / 2
    # 计算蓝色分量
    blue = (math.sin(2 * math.pi * (t + 2 / 3)) + 1) / 2
    return glm.vec3(red, green, blue)


class WaypointList(list[Waypoint]):
    last_tid = -1

    def append_waypoint(self, pos: glm.vec3 | typing.Callable[[Waypoint], glm.vec3], pop_mode=Waypoint.POP_MANUAL, reach_dis=Waypoint.REACH_DIS, auto_pop=-1., surface_color: glm.vec3 = None, line_color: glm.vec3 = None):
        w = Waypoint(self, pos, pop_mode, reach_dis, auto_pop, surface_color, line_color)
        if not self or auto_pop <= 0:
            self.append(w)
        else:
            for i, _w in enumerate(self):
                if _w.pop_at <= 0 or _w.pop_at > w.pop_at:
                    self.insert(i + 1, w)
                    break
            else:
                self.append(w)
        return w

    def set_waypoint(self, *pos: glm.vec3, pop_mode=Waypoint.POP_WHEN_REACH):
        self.clear()
        return [self.append_waypoint(p, pop_mode) for p in pos]

    def update(self):
        if (tid := main.mem.territory_info.territory_id) != self.last_tid:
            self.last_tid = tid
            self.clear()
            return
        if not self: return
        if not (me := get_me()): return
        me_pos = me.pos
        while self:
            try:
                next_waypoint = self[0]
            except IndexError:
                return
            if next_waypoint.should_pop(me_pos):
                next_waypoint.pop()
            else:
                break

    def render_game(self):
        if not self: return
        if not (me := get_me()): return
        prev_pt = me_pos = me.pos
        i = 0
        current = time.time()
        cos_a = (math.cos(current * 4) + 1) * .3 + .1
        default_color = color_gradient(current)
        while i < len(self):
            next_wp: Waypoint = self[i]
            wp_pos = next_wp.pos
            if wp_pos is None:
                i += 1
                continue
            surface_color = next_wp.surface_color or default_color
            line_color = next_wp.line_color or default_color
            if next_wp.is_reach(me_pos):
                main.gui.add_3d_shape(
                    circle_shape(),
                    glm.translate(wp_pos) * glm.scale(glm.vec3(next_wp.reach_dis)),
                    surface_color=glm.vec4(surface_color, .35), line_color=glm.vec4(line_color, .7)
                )
            else:
                main.gui.add_3d_shape(
                    donut_shape(.5, 1),
                    glm.translate(wp_pos) * glm.scale(glm.vec3(next_wp.reach_dis)),
                    surface_color=glm.vec4(surface_color, cos_a / 2), line_color=glm.vec4(line_color, cos_a),
                )
                main.gui.add_line(prev_pt, wp_pos, glm.vec4(line_color, .7), width=5)
                if i == 0:
                    main.gui.add_3d_shape(
                        0x1010000,
                        glm.translate(prev_pt) * glm.rotate(glm.polar(wp_pos - me_pos).y, glm.vec3(0, 1, 0)),
                        surface_color=glm.vec4(surface_color, .35), line_color=glm.vec4(line_color, .7),
                    )
            prev_pt = wp_pos
            i += 1
