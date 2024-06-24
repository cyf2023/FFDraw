from .types import *


class Emitter(AVfxStruct):
    _emitter_variety_type = KeyAttr.simple(b'EVT', 0, s_int8)
    _rotation_base_direction_type = KeyAttr.simple(b'RBDT', 0, s_int8)
    _rotation_order_type = KeyAttr.simple(b'ROT', 0, s_int8)
    _coordinate_compute_order_type = KeyAttr.simple(b'CCOT', 0, s_int8)
    emitter_variety_type = enum_property(EmitterVarietyType, '_emitter_variety_type')
    rotation_base_direction_type = enum_property(RotationBaseDirectionType, '_rotation_base_direction_type')
    rotation_order_type = enum_property(RotationOrderType, '_rotation_order_type')
    coordinate_compute_order_type = enum_property(CoordinateComputeOrderType, '_coordinate_compute_order_type')
    loop_point_start = KeyAttr.simple(b'LpSt', 0, s_int16)
    loop_point_goal = KeyAttr.simple(b'LpEd', 0, s_int16)
    child_limit_count = KeyAttr.simple(b'ClCn', -1, s_int16)
    effector_no = KeyAttr.simple(b'EfNo', -1, s_int8)
    sound_file_name = KeyAttr.string(b'SdNm')
    sound_no = KeyAttr.simple(b'SdNo', 0, s_int32)
    is_any_direction = KeyAttr.bool(b'bAD', False, s_int32)
    injection_axis_x = ValueFunctionCurveAttr.make(b'IAX', b'IAXR')
    injection_axis_y = ValueFunctionCurveAttr.make(b'IAY', b'IAYR')
    injection_axis_z = ValueFunctionCurveAttr.make(b'IAZ', b'IAZR')
    create_count = ValueFunctionCurveAttr.make(b'CrC', b'CrCR')
    create_interval = ValueFunctionCurveAttr.make(b'CrI', b'CrIR')
    gravity = ValueFunctionCurveAttr.make(b'Gra', b'GraR')
    air_resistance = ValueFunctionCurveAttr.make(b'ARs', b'ARsR')
    particles = KeyListAttr.struct(b'PrCn', b'ItPr', CreateItem)
    emitter = KeyListAttr.struct(b'EmCn', b'ItEm', CreateItem)
    life = KeyAttr.struct(b'Life', Value)
    color = KeyAttr.struct(b'Col', ColorFunctionCurve)
    position = KeyAttr.struct(b'Pos', Axis3Parameter)
    rotation = KeyAttr.struct(b'Rot', Axis3Parameter)
    scale = KeyAttr.struct(b'Scl', Axis3Parameter)
    velocity_rotation_x = ValueFunctionCurveAttr.make(b'VRX', b'VRXR')
    velocity_rotation_y = ValueFunctionCurveAttr.make(b'VRY', b'VRYR')
    velocity_rotation_z = ValueFunctionCurveAttr.make(b'VRZ', b'VRZR')

    # TODO: b'Data'
    data = KeyAttr.make(b'Data', dumb_loader, dumb_packer, b'')
