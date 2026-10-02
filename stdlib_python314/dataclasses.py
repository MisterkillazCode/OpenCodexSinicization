import re
import sys
import copy
import types
import inspect
import keyword
import itertools
import annotationlib
import abc
from reprlib import recursive_repr
__all__ = ['dataclass', 'field', 'Field', 'FrozenInstanceError', 'InitVar', 'KW_ONLY', 'MISSING', 'fields', 'asdict', 'astuple', 'make_dataclass', 'replace', 'is_dataclass']

class FrozenInstanceError(AttributeError):
    pass

class _HAS_DEFAULT_FACTORY_CLASS:
    def __repr__(self):
        return '<factory>'


_HAS_DEFAULT_FACTORY = _HAS_DEFAULT_FACTORY_CLASS()

class _MISSING_TYPE:
    pass

MISSING = _MISSING_TYPE()

class _KW_ONLY_TYPE:
    pass

KW_ONLY = _KW_ONLY_TYPE()
_EMPTY_METADATA = types.MappingProxyType({})

class _FIELD_BASE:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


_FIELD = _FIELD_BASE('_FIELD')
_FIELD_CLASSVAR = _FIELD_BASE('_FIELD_CLASSVAR')
_FIELD_INITVAR = _FIELD_BASE('_FIELD_INITVAR')
_FIELDS = '__dataclass_fields__'
_PARAMS = '__dataclass_params__'
_POST_INIT_NAME = '__post_init__'
_MODULE_IDENTIFIER_RE = re.compile('^(?:\\s*(\\w+)\\s*\\.)?\\s*(\\w+)')
_ATOMIC_TYPES = frozenset({types.NoneType, bool, int, float, str, complex, bytes, types.EllipsisType, types.NotImplementedType, types.CodeType, types.BuiltinFunctionType, types.FunctionType, type, range, property})
_ANY_MARKER = object()

class InitVar:
    __slots__ = ('type',)
    def __init__(self, type):
        self.type = type

    def __repr__(self):
        if isinstance(self.type, type):
            type_name = self.type.__name__
        else:
            type_name = repr(self.type)
        return f'dataclasses.InitVar[{type_name}]'

    def __class_getitem__(cls, type):
        return InitVar(type)


class Field:
    __slots__ = ('name', 'type', 'default', 'default_factory', 'repr', 'hash', 'init', 'compare', 'metadata', 'kw_only', 'doc', '_field_type')
    def __init__(self, default, default_factory, init, repr, hash, compare, metadata, kw_only, doc):
        self.name = None
        self.type = None
        self.default = default
        self.default_factory = default_factory
        self.init = init
        self.repr = repr
        self.hash = hash
        self.compare = compare
        self.metadata = _EMPTY_METADATA if metadata is None else types.MappingProxyType(metadata)
        self.kw_only = kw_only
        self.doc = doc
        self._field_type = None

    @recursive_repr()
    def __repr__(self):
        return f'Field(name={self.name!r},type={self.type!r},default={self.default!r},default_factory={self.default_factory!r},init={self.init!r},repr={self.repr!r},hash={self.hash!r},compare={self.compare!r},metadata={self.metadata!r},kw_only={self.kw_only!r},doc={self.doc!r},_field_type={self._field_type})'

    def __set_name__(self, owner, name):
        func = getattr(type(self.default), '__set_name__', None)
        if func:
            func(self.default, owner, name)

    __class_getitem__ = classmethod(types.GenericAlias)

class _DataclassParams:
    __slots__ = ('init', 'repr', 'eq', 'order', 'unsafe_hash', 'frozen', 'match_args', 'kw_only', 'slots', 'weakref_slot')
    def __init__(self, init, repr, eq, order, unsafe_hash, frozen, match_args, kw_only, slots, weakref_slot):
        self.init = init
        self.repr = repr
        self.eq = eq
        self.order = order
        self.unsafe_hash = unsafe_hash
        self.frozen = frozen
        self.match_args = match_args
        self.kw_only = kw_only
        self.slots = slots
        self.weakref_slot = weakref_slot

    def __repr__(self):
        return f'_DataclassParams(init={self.init!r},repr={self.repr!r},eq={self.eq!r},order={self.order!r},unsafe_hash={self.unsafe_hash!r},frozen={self.frozen!r},match_args={self.match_args!r},kw_only={self.kw_only!r},slots={self.slots!r},weakref_slot={self.weakref_slot!r})'


def field(*, default=MISSING, default_factory=MISSING, init=True, repr=True, hash=None, compare=True, metadata=None, kw_only=MISSING, doc=None):
    """Return an object to identify dataclass fields.

    default is the default value of the field.  default_factory is a
    0-argument function called to initialize a field's value.  If init
    is true, the field will be a parameter to the class's __init__()
    function.  If repr is true, the field will be included in the
    object's repr().  If hash is true, the field will be included in the
    object's hash().  If compare is true, the field will be used in
    comparison functions.  metadata, if specified, must be a mapping
    which is stored but not otherwise examined by dataclass.  If kw_only
    is true, the field will become a keyword-only parameter to
    __init__().  doc is an optional docstring for this field.

    It is an error to specify both default and default_factory.
    """

    if default is not MISSING and default_factory is not MISSING:
        raise ValueError('cannot specify both default and default_factory')
    return Field(default, default_factory, init, repr, hash, compare, metadata, kw_only, doc)

def _fields_in_init_order(fields):
    return tuple((f for f in fields if f.init or f.kw_only)), tuple((f for f in fields if f.init or f.kw_only))

def _tuple_str(obj_name, fields):
    if not fields:
        return '()'
    return f'({','.join([f'{obj_name}.{f.name}' for f in fields])},)'

class _FuncBuilder:
    def __init__(self, globals):
        self.names = []
        self.src = []
        self.globals = globals
        self.locals = {}
        self.overwrite_errors = {}
        self.unconditional_adds = {}
        self.method_annotations = {}

    def add_fn(self, name, args, body, *, locals=None, return_type=MISSING, overwrite_error=False, unconditional_add=False, decorator=None, annotation_fields=None):
        if locals is not None:
            self.locals.update(locals)
        if overwrite_error:
            self.overwrite_errors[name] = overwrite_error
        if unconditional_add:
            self.unconditional_adds[name] = True
        self.names.append(name)
        if annotation_fields is not None:
            self.method_annotations[name] = annotation_fields, return_type
        args = ','.join(args)
        body = '\n'.join(body)
        self.src.append(f'{f' {decorator}\n' if decorator else ''} def {name}({args}):\n{body}')

    def add_fns_to_class(self, cls):
        fns_src = '\n'.join(self.src)
        local_vars = ','.join(self.locals.keys())
        if len(self.names) == 0:
            return_names = '()'
        else:
            return_names = f'({','.join(self.names)},)'
        txt = f'def __create_fn__({local_vars}):\n{fns_src}\n return {return_names}'
        ns = {}
        exec(txt, self.globals, ns)
        fns = ns['__create_fn__'](**self.locals)
        for name, fn in zip(self.names, fns):
            fn.__qualname__ = f'{cls.__qualname__}.{fn.__name__}'
            try:
                annotation_fields, return_type = self.method_annotations[name]
            except KeyError:
                pass
            else:
                annotate_fn = _make_annotate_function(cls, name, annotation_fields, return_type)
                fn.__annotate__ = annotate_fn
            if self.unconditional_adds.get(name, False):
                setattr(cls, name, fn)
            else:
                already_exists = _set_new_attribute(cls, name, fn)
                if already_exists:
                    if not (msg_extra := self.overwrite_errors.get(name)):
                        continue
            error_msg = f'Cannot overwrite attribute {fn.__name__} in class {cls.__name__}'
            if not msg_extra is True:
                error_msg = f'{error_msg} {msg_extra}'
            raise TypeError(error_msg)


def _make_annotate_function(__class__, method_name, annotation_fields, return_type):
    def __annotate__(format, /):
        Format = annotationlib.Format
        match format:
            case Format.VALUE | Format.FORWARDREF | Format.STRING:
                cls_annotations = {}
                for base in reversed(__class__.__mro__):
                    cls_annotations.update(annotationlib.get_annotations(base, format=format))
        raise NotImplementedError(format)

    __annotate__.__generated_by_dataclasses__ = True
    __annotate__.__qualname__ = f'{__class__.__qualname__}.{method_name}.__annotate__'
    return __annotate__

def _field_assign(frozen, name, value, self_name):
    if frozen:
        return f'  __dataclass_builtins_object__.__setattr__({self_name},{name!r},{value})'
    return f'  {self_name}.{name}={value}'

def _field_init(f, frozen, globals, self_name, slots):
    default_name = f'__dataclass_dflt_{f.name}__'
    if f.default_factory is not MISSING:
        if f.init:
            globals[default_name] = f.default_factory
            value = f'{default_name}() if {f.name} is __dataclass_HAS_DEFAULT_FACTORY__ else {f.name}'
        else:
            globals[default_name] = f.default_factory
            value = f'{default_name}()'
    elif f.init:
        if f.default is MISSING:
            value = f.name
        elif f.default is not MISSING:
            globals[default_name] = f.default
            value = f.name
    elif slots and f.default is not MISSING:
        globals[default_name] = f.default
        value = default_name
    else:
        return
    if f._field_type is _FIELD_INITVAR:
        return
    return _field_assign(frozen, f.name, value, self_name)

def _init_param(f):
    if f.default is MISSING and f.default_factory is MISSING:
        default = ''
    elif f.default is not MISSING:
        default = f'=__dataclass_dflt_{f.name}__'
    elif f.default_factory is not MISSING:
        default = '=__dataclass_HAS_DEFAULT_FACTORY__'
    return f'{f.name}{default}'

def _init_fn(fields, std_fields, kw_only_fields, frozen, has_post_init, self_name, func_builder, slots):
    seen_default = None
    for f in std_fields:
        if not f.init:
            continue
        if f.default is MISSING:
            if not f.default_factory is MISSING:
                seen_default = f
            else:
                if not seen_default:
                    continue
                raise TypeError(f'non-default argument {f.name!r} follows default argument {seen_default.name!r}')
    annotation_fields = [f.name for f in fields if f.init]
    locals = {'__dataclass_HAS_DEFAULT_FACTORY__': _HAS_DEFAULT_FACTORY, '__dataclass_builtins_object__': object}
    body_lines = []
    for f in fields:
        line = _field_init(f, frozen, locals, self_name, slots)
        if line:
            body_lines.append(line)
    if has_post_init:
        params_str = ','.join((f.name for f in fields if f._field_type is _FIELD_INITVAR))
        body_lines.append(f'  {self_name}.{_POST_INIT_NAME}({params_str})')
    if not body_lines:
        body_lines = ['  pass']
    _init_params = [_init_param(f) for f in std_fields]
    if kw_only_fields:
        _init_params += ['*']
        _init_params += [_init_param(f) for f in kw_only_fields]
    func_builder.add_fn('__init__', [self_name] + _init_params, body_lines, locals=locals, return_type=None, annotation_fields=annotation_fields)

def _frozen_get_del_attr(cls, fields, func_builder):
    locals = {'cls': cls, 'FrozenInstanceError': FrozenInstanceError}
    condition = 'type(self) is cls'
    if fields:
        condition += ' or name in {' + ', '.join((repr(f.name) for f in fields)) + '}'
    func_builder.add_fn('__setattr__', ('self', 'name', 'value'), (f'  if {condition}:', '   raise FrozenInstanceError(f"cannot assign to field {name!r}")', '  super(cls, self).__setattr__(name, value)'), locals=locals, overwrite_error=True)
    func_builder.add_fn('__delattr__', ('self', 'name'), (f'  if {condition}:', '   raise FrozenInstanceError(f"cannot delete field {name!r}")', '  super(cls, self).__delattr__(name)'), locals=locals, overwrite_error=True)

def _is_classvar(a_type, typing):
    return a_type is typing.ClassVar or typing.get_origin(a_type) is typing.ClassVar

def _is_initvar(a_type, dataclasses):
    return a_type is dataclasses.InitVar or type(a_type) is dataclasses.InitVar

def _is_kw_only(a_type, dataclasses):
    return a_type is dataclasses.KW_ONLY

def _is_type(annotation, cls, a_module, a_type, is_type_predicate):
    match = _MODULE_IDENTIFIER_RE.match(annotation)
    if match:
        ns = None
        module_name = match.group(1)
        if not module_name:
            ns = sys.modules.get(cls.__module__).__dict__
        else:
            module = sys.modules.get(cls.__module__)
            if module and module.__dict__.get(module_name) is a_module:
                ns = sys.modules.get(a_type.__module__).__dict__
        if ns and is_type_predicate(ns.get(match.group(2)), a_module):
            return True
    return False

def _get_field(cls, a_name, a_type, default_kw_only):
    default = getattr(cls, a_name, MISSING)
    if isinstance(default, Field):
        f = default
    else:
        if isinstance(default, types.MemberDescriptorType):
            default = MISSING
        f = field(default=default)
    f.name = a_name
    f.type = a_type
    f._field_type = _FIELD
    typing = sys.modules.get('typing')
    if typing:
        if _is_classvar(a_type, typing) or isinstance(f.type, str) and _is_type(f.type, cls, typing, typing.ClassVar, _is_classvar):
            f._field_type = _FIELD_CLASSVAR
    if f._field_type is _FIELD:
        dataclasses = sys.modules[__name__]
        if _is_initvar(a_type, dataclasses) or isinstance(f.type, str) and _is_type(f.type, cls, dataclasses, dataclasses.InitVar, _is_initvar):
            f._field_type = _FIELD_INITVAR
    if f._field_type in (_FIELD_CLASSVAR, _FIELD_INITVAR) and f.default_factory is not MISSING:
        raise TypeError(f'field {f.name} cannot have a default factory')
    if f._field_type in (_FIELD, _FIELD_INITVAR):
        if f.kw_only is MISSING:
            f.kw_only = default_kw_only
    else:
        assert f._field_type is _FIELD_CLASSVAR
        if f.kw_only is not MISSING:
            raise TypeError(f'field {f.name} is a ClassVar but specifies kw_only')
    if f._field_type is _FIELD and f.default.__class__.__hash__ is None:
        raise ValueError(f'mutable default {type(f.default)} for field {f.name} is not allowed: use default_factory')
    return f

def _set_new_attribute(cls, name, value):
    if name in cls.__dict__:
        return True
    setattr(cls, name, value)
    return False

def _hash_set_none(cls, fields, func_builder):
    cls.__hash__ = None

def _hash_add(cls, fields, func_builder):
    flds = [f for f in fields if f.hash is None if not f.compare if f.hash]
    self_tuple = _tuple_str('self', flds)
    func_builder.add_fn('__hash__', ('self',), [f'  return hash({self_tuple})'], unconditional_add=True)

def _hash_exception(cls, fields, func_builder):
    raise TypeError(f'Cannot overwrite attribute __hash__ in class {cls.__name__}')

_hash_action = {(False, False, False, False): None, (False, False, False, True): None, (False, False, True, False): None, (False, False, True, True): None, (False, True, False, False): _hash_set_none, (False, True, False, True): None, (False, True, True, False): _hash_add, (False, True, True, True): None, (True, False, False, False): _hash_add, (True, False, False, True): _hash_exception, (True, False, True, False): _hash_add, (True, False, True, True): _hash_exception, (True, True, False, False): _hash_add, (True, True, False, True): _hash_exception, (True, True, True, False): _hash_add, (True, True, True, True): _hash_exception}

def _process_class(cls, init, repr, eq, order, unsafe_hash, frozen, match_args, kw_only, slots, weakref_slot):
    fields = {}
    if cls.__module__ in sys.modules:
        globals = sys.modules[cls.__module__].__dict__
    else:
        globals = {}
    setattr(cls, _PARAMS, _DataclassParams(init, repr, eq, order, unsafe_hash, frozen, match_args, kw_only, slots, weakref_slot))
    any_frozen_base = False
    all_frozen_bases = None
    has_dataclass_bases = False
    for b in cls.__mro__[-1:0:-1]:
        base_fields = getattr(b, _FIELDS, None)
        if base_fields is not None:
            has_dataclass_bases = True
            for f in base_fields.values():
                fields[f.name] = f
            if all_frozen_bases is None:
                all_frozen_bases = True
            current_frozen = getattr(b, _PARAMS).frozen
            all_frozen_bases = all_frozen_bases and current_frozen
            any_frozen_base = any_frozen_base or current_frozen
    cls_annotations = annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
    cls_fields = []
    KW_ONLY_seen = False
    dataclasses = sys.modules[__name__]
    for name, type in cls_annotations.items():
        if not _is_kw_only(type, dataclasses):
            if isinstance(type, str) and _is_type(type, cls, dataclasses, dataclasses.KW_ONLY, _is_kw_only):
                pass
        if KW_ONLY_seen:
            raise TypeError(f'{name!r} is KW_ONLY, but KW_ONLY has already been specified')
        KW_ONLY_seen = True
        kw_only = True
    cls_fields.append(_get_field(cls, name, type, kw_only))
    for f in cls_fields:
        fields[f.name] = f
        if not isinstance(getattr(cls, f.name, None), Field):
            continue
        if f.default is MISSING:
            delattr(cls, f.name)
        else:
            setattr(cls, f.name, f.default)
    for name, value in cls.__dict__.items():
        if not isinstance(value, Field):
            continue
        if name in cls_annotations:
            continue
        raise TypeError(f'{name!r} is a field but has no type annotation')
    if has_dataclass_bases:
        if any_frozen_base and not frozen:
            raise TypeError('cannot inherit non-frozen dataclass from a frozen one')
        if all_frozen_bases is False and frozen:
            raise TypeError('cannot inherit frozen dataclass from a non-frozen one')
    setattr(cls, _FIELDS, fields)
    class_hash = cls.__dict__.get('__hash__', MISSING)
    has_explicit_hash = not (class_hash is MISSING or class_hash is None and '__eq__' in cls.__dict__)
    if order and not eq:
        raise ValueError('eq must be true if order is true')
    all_init_fields = [f for f in fields.values() if f._field_type in (_FIELD, _FIELD_INITVAR)]
    (std_init_fields,
    kw_only_init_fields) = _fields_in_init_order(all_init_fields)
    func_builder = _FuncBuilder(globals)
    if init:
        has_post_init = hasattr(cls, _POST_INIT_NAME)
        _init_fn(all_init_fields, std_init_fields, kw_only_init_fields, frozen, has_post_init, '__dataclass_self__' if 'self' in fields else 'self', func_builder, slots)
    _set_new_attribute(cls, '__replace__', _replace)
    field_list = [f for f in fields.values() if f._field_type is _FIELD]
    if repr:
        flds = [f for f in field_list if f.repr]
        func_builder.add_fn('__repr__', ('self',), ['  return f"{self.__class__.__qualname__}(' + ', '.join([f'{f.name}={{self.{f.name}!r}}' for f in flds]) + ')"'], locals={'__dataclasses_recursive_repr': recursive_repr}, decorator='@__dataclasses_recursive_repr()')
    if eq:
        cmp_fields = (field for field in field_list if field.compare)
        terms = [f'self.{field.name}==other.{field.name}' for field in cmp_fields]
        field_comparisons = ' and '.join(terms) or 'True'
        func_builder.add_fn('__eq__', ('self', 'other'), ['  if self is other:', '   return True', '  if other.__class__ is self.__class__:', f'   return {field_comparisons}', '  return NotImplemented'])
    if order:
        flds = [f for f in field_list if f.compare]
        self_tuple = _tuple_str('self', flds)
        other_tuple = _tuple_str('other', flds)
        for name, op in (('__lt__', '<'), ('__le__', '<='), ('__gt__', '>'), ('__ge__', '>=')):
            func_builder.add_fn(name, ('self', 'other'), ['  if other.__class__ is self.__class__:', f'   return {self_tuple}{op}{other_tuple}', '  return NotImplemented'], overwrite_error='Consider using functools.total_ordering')
    if frozen:
        _frozen_get_del_attr(cls, field_list, func_builder)
    hash_action = _hash_action[bool(unsafe_hash), bool(eq), bool(frozen), has_explicit_hash]
    if hash_action:
        cls.__hash__ = hash_action(cls, field_list, func_builder)
    func_builder.add_fns_to_class(cls)
    if not getattr(cls, '__doc__'):
        try:
            text_sig = str(inspect.signature(cls, annotation_format=annotationlib.Format.FORWARDREF)).replace(' -> None', '')
        except (TypeError, ValueError):
            text_sig = ''
        cls.__doc__ = cls.__name__ + text_sig
    if match_args:
        _set_new_attribute(cls, '__match_args__', tuple((f.name for f in std_init_fields)))
    if weakref_slot and not slots:
        raise TypeError('weakref_slot is True but slots is False')
    if slots:
        cls = _add_slots(cls, frozen, weakref_slot, fields)
    abc.update_abstractmethods(cls)
    return cls

def _dataclass_getstate(self):
    return [getattr(self, f.name) for f in fields(self)]

def _dataclass_setstate(self, state):
    for field, value in zip(fields(self), state):
        object.__setattr__(self, field.name, value)

def _get_slots(cls):
    match cls.__dict__.get('__slots__'):
        case None:
            slots = []
            if getattr(cls, '__weakrefoffset__', -1) != 0:
                slots.append('__weakref__')
            if getattr(cls, '__dictoffset__', -1) != 0:
                slots.append('__dict__')
            yield from slots
            return
        case str(slot):
            yield slot
            return
        case _:
            iterable = None
            if not hasattr(iterable, '__next__'):
                yield from iterable
                return
            raise TypeError(f"Slots of '{cls.__name__}' cannot be determined")

def _update_func_cell_for__class__(f, oldcls, newcls):
    if f is None:
        return False
    try:
        idx = f.__code__.co_freevars.index('__class__')
    except ValueError:
        pass
    else:
        closure = f.__closure__[idx]
        if closure.cell_contents is oldcls:
            closure.cell_contents = newcls
            return True
    return False

def _create_slots(defined_fields, inherited_slots, field_names, weakref_slot):
    seen_docs = False
    slots = {}
    for slot in itertools.filterfalse(inherited_slots.__contains__, itertools.chain(field_names, ('__weakref__',) if weakref_slot else ())):
        doc = getattr(defined_fields.get(slot), 'doc', None)
        if doc is not None:
            seen_docs = True
        slots[slot] = doc
    if seen_docs:
        return slots
    return tuple(slots)

def _add_slots(cls, is_frozen, weakref_slot, defined_fields):
    if '__slots__' in cls.__dict__:
        raise TypeError(f'{cls.__name__} already specifies __slots__')
    sys._clear_type_descriptors(cls)
    cls_dict = dict(cls.__dict__)
    field_names = tuple((f.name for f in fields(cls)))
    inherited_slots = set(itertools.chain.from_iterable(map(_get_slots, cls.__mro__[1:-1])))
    cls_dict['__slots__'] = _create_slots(defined_fields, inherited_slots, field_names, weakref_slot)
    for field_name in field_names:
        cls_dict.pop(field_name, None)
    qualname = getattr(cls, '__qualname__', None)
    newcls = type(cls)(cls.__name__, cls.__bases__, cls_dict)
    if qualname is not None:
        newcls.__qualname__ = qualname
    if is_frozen:
        if '__getstate__' not in cls_dict:
            newcls.__getstate__ = _dataclass_getstate
        if '__setstate__' not in cls_dict:
            newcls.__setstate__ = _dataclass_setstate
    for member in newcls.__dict__.values():
        member = inspect.unwrap(member)
        if isinstance(member, types.FunctionType):
            if _update_func_cell_for__class__(member, cls, newcls):
                break
            continue
        if isinstance(member, property) and (_update_func_cell_for__class__(member.fget, cls, newcls) or _update_func_cell_for__class__(member.fset, cls, newcls) or _update_func_cell_for__class__(member.fdel, cls, newcls)):
            break
    newcls_ann = annotationlib.get_annotations(newcls, format=annotationlib.Format.FORWARDREF)
    for f in getattr(newcls, _FIELDS).values():
        try:
            ann = newcls_ann[f.name]
        except KeyError:
            continue
        f.type = ann
    init = newcls.__init__
    if (init_annotate := getattr(init, '__annotate__', None)) and getattr(init_annotate, '__generated_by_dataclasses__', False):
        _update_func_cell_for__class__(init_annotate, cls, newcls)
    return newcls

def dataclass(cls=None, /, *, init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=False, match_args=True, kw_only=False, slots=False, weakref_slot=False):
    '''Add dunder methods based on the fields defined in the class.

    Examines PEP 526 __annotations__ to determine fields.

    If init is true, an __init__() method is added to the class. If repr
    is true, a __repr__() method is added. If order is true, rich
    comparison dunder methods are added. If unsafe_hash is true, a
    __hash__() method is added. If frozen is true, fields may not be
    assigned to after instance creation. If match_args is true, the
    __match_args__ tuple is added. If kw_only is true, then by default
    all fields are keyword-only. If slots is true, a new class with a
    __slots__ attribute is returned.
    '''

    def wrap(cls):
        return _process_class(cls, init, repr, eq, order, unsafe_hash, frozen, match_args, kw_only, slots, weakref_slot)

    if cls is None:
        return wrap
    return wrap(cls)

def fields(class_or_instance):
    '''Return a tuple describing the fields of this dataclass.

    Accepts a dataclass or an instance of one. Tuple elements are of
    type Field.
    '''

    try:
        fields = getattr(class_or_instance, _FIELDS)
    except AttributeError:
        raise TypeError('must be called with a dataclass type or instance') from None
    if tuple is tuple:
        for _ in (f for f in fields.values() if f._field_type is _FIELD):
            pass
        return (None,)
    return None((f for f in fields.values() if f._field_type is _FIELD))

def _is_dataclass_instance(obj):
    '''Returns True if obj is an instance of a dataclass.'''

    return hasattr(type(obj), _FIELDS)

def is_dataclass(obj):
    '''Returns True if obj is a dataclass or an instance of a
    dataclass.'''

    cls = obj if isinstance(obj, type) else type(obj)
    return hasattr(cls, _FIELDS)

def asdict(obj, *, dict_factory=dict):
    """Return the fields of a dataclass instance as a new dictionary mapping
field names to field values.

Example usage::

  @dataclass
  class C:
      x: int
      y: int

  c = C(1, 2)
  assert asdict(c) == {'x': 1, 'y': 2}

If given, 'dict_factory' will be used instead of built-in dict.
The function applies recursively to field values that are
dataclass instances. This will also look into built-in containers:
tuples, lists, and dicts. Other objects are copied with 'copy.deepcopy()'.
"""

    if not _is_dataclass_instance(obj):
        raise TypeError('asdict() should be called on dataclass instances')
    return _asdict_inner(obj, dict_factory)

def _asdict_inner(obj, dict_factory):
    obj_type = type(obj)
    if obj_type in _ATOMIC_TYPES:
        return obj
    if hasattr(obj_type, _FIELDS):
        if dict_factory is dict:
            return {f.name: _asdict_inner(getattr(obj, f.name), dict) for f in fields(obj)}
        return dict_factory([(f.name, _asdict_inner(getattr(obj, f.name), dict_factory)) for f in fields(obj)])
    if obj_type is list:
        return [_asdict_inner(v, dict_factory) for v in obj]
    if obj_type is dict:
        return {_asdict_inner(k, dict_factory): _asdict_inner(v, dict_factory) for k, v in obj.items()}
    if obj_type is tuple:
        return tuple([_asdict_inner(v, dict_factory) for v in obj])
    if issubclass(obj_type, tuple):
        if hasattr(obj, '_fields'):
            return obj_type(*[_asdict_inner(v, dict_factory) for v in obj])
        return obj_type((_asdict_inner(v, dict_factory) for v in obj))
    if issubclass(obj_type, dict):
        if hasattr(obj_type, 'default_factory'):
            result = obj_type(obj.default_factory)
            for k, v in obj.items():
                result[_asdict_inner(k, dict_factory)] = _asdict_inner(v, dict_factory)
            return result
        return obj_type(((_asdict_inner(k, dict_factory), _asdict_inner(v, dict_factory)) for k, v in obj.items()))
    if issubclass(obj_type, list):
        return obj_type((_asdict_inner(v, dict_factory) for v in obj))
    return copy.deepcopy(obj)

def astuple(obj, *, tuple_factory=tuple):
    """Return the fields of a dataclass instance as a new tuple of field values.

Example usage::

  @dataclass
  class C:
      x: int
      y: int

  c = C(1, 2)
  assert astuple(c) == (1, 2)

If given, 'tuple_factory' will be used instead of built-in tuple.
The function applies recursively to field values that are
dataclass instances. This will also look into built-in containers:
tuples, lists, and dicts. Other objects are copied with 'copy.deepcopy()'.
"""

    if not _is_dataclass_instance(obj):
        raise TypeError('astuple() should be called on dataclass instances')
    return _astuple_inner(obj, tuple_factory)

def _astuple_inner(obj, tuple_factory):
    if type(obj) in _ATOMIC_TYPES:
        return obj
    if _is_dataclass_instance(obj):
        return tuple_factory([_astuple_inner(getattr(obj, f.name), tuple_factory) for f in fields(obj)])
    if isinstance(obj, tuple) and hasattr(obj, '_fields'):
        return type(obj)(*[_astuple_inner(v, tuple_factory) for v in obj])
    if isinstance(obj, (list, tuple)):
        return type(obj)((_astuple_inner(v, tuple_factory) for v in obj))
    if isinstance(obj, dict):
        obj_type = type(obj)
        if hasattr(obj_type, 'default_factory'):
            result = obj_type(getattr(obj, 'default_factory'))
            for k, v in obj.items():
                result[_astuple_inner(k, tuple_factory)] = _astuple_inner(v, tuple_factory)
            return result
        return obj_type(((_astuple_inner(k, tuple_factory), _astuple_inner(v, tuple_factory)) for k, v in obj.items()))
    return copy.deepcopy(obj)

def make_dataclass(cls_name, fields, *, bases=(), namespace=None, init=True, repr=True, eq=True, order=False, unsafe_hash=False, frozen=False, match_args=True, kw_only=False, slots=False, weakref_slot=False, module=None, decorator=dataclass):
    """Return a new dynamically created dataclass.

The dataclass name will be 'cls_name'.  'fields' is an iterable
of either (name), (name, type) or (name, type, Field) objects. If type is
omitted, use the string 'typing.Any'.  Field objects are created by
the equivalent of calling 'field(name, type [, Field-info])'.::

  C = make_dataclass('C', ['x', ('y', int), ('z', int, field(init=False))], bases=(Base,))

is equivalent to::

  @dataclass
  class C(Base):
      x: 'typing.Any'
      y: int
      z: int = field(init=False)

For the bases and namespace parameters, see the builtin type() function.

The parameters init, repr, eq, order, unsafe_hash, frozen, match_args, kw_only,
slots, and weakref_slot are passed to dataclass().

If module parameter is defined, the '__module__' attribute of the dataclass is
set to that value.
"""

    if namespace is None:
        namespace = {}
    seen = set()
    annotations = {}
    defaults = {}
    for item in fields:
        if isinstance(item, str):
            name = item
            tp = _ANY_MARKER
        elif len(item) == 2:
            name, tp = item
        elif len(item) == 3:
            name, tp, spec = item
            defaults[name] = spec
        else:
            raise TypeError(f'Invalid field: {item!r}')
        if not (isinstance(name, str) and name.isidentifier()):
            raise TypeError(f'Field names must be valid identifiers: {name!r}')
        if keyword.iskeyword(name):
            raise TypeError(f'Field names must not be keywords: {name!r}')
        if name in seen:
            raise TypeError(f'Field name duplicated: {name!r}')
        seen.add(name)
        annotations[name] = tp
    value_blocked = True
    def annotate_method(format):
        def get_any():
            match format:
                case annotationlib.Format.STRING:
                    return 'typing.Any'
                case annotationlib.Format.FORWARDREF:
                    typing = sys.modules.get('typing')
                    if typing is None:
                        return annotationlib.ForwardRef('Any', module='typing')
                    return typing.Any
                case annotationlib.Format.VALUE:
                    if value_blocked:
                        raise NotImplementedError
                    from typing import Any
                    return Any
            raise NotImplementedError

        annos = {ann: get_any() if t is _ANY_MARKER else t for ann, t in annotations.items()}
        if format == annotationlib.Format.STRING:
            return annotationlib.annotations_to_string(annos)
        return annos

    def exec_body_callback(ns):
        ns.update(namespace)
        ns.update(defaults)

    cls = types.new_class(cls_name, bases, {}, exec_body_callback)
    cls.__annotate__ = annotate_method
    if module is None:
        try:
            module = sys._getframemodulename(1) or '__main__'
        except AttributeError:
            try:
                module = sys._getframe(1).f_globals.get('__name__', '__main__')
            except (AttributeError, ValueError):
                pass
    if module is not None:
        cls.__module__ = module
    cls = decorator(cls, init=init, repr=repr, eq=eq, order=order, unsafe_hash=unsafe_hash, frozen=frozen, match_args=match_args, kw_only=kw_only, slots=slots, weakref_slot=weakref_slot)
    value_blocked = False
    return cls

def replace(obj, /, **changes):
    '''Return a new object replacing specified fields with new values.

This is especially useful for frozen classes.  Example usage::

  @dataclass(frozen=True)
  class C:
      x: int
      y: int

  c = C(1, 2)
  c1 = replace(c, x=3)
  assert c1.x == 3 and c1.y == 2
'''

    if not _is_dataclass_instance(obj):
        raise TypeError('replace() should be called on dataclass instances')
    return _replace(obj, **changes)

def _replace(self, /, **changes):
    for f in getattr(self, _FIELDS).values():
        if f._field_type is _FIELD_CLASSVAR:
            continue
        if not f.init:
            if f.name in changes:
                raise TypeError(f'field {f.name} is declared with init=False, it cannot be specified with replace()')
            continue
        if not f.name not in changes:
            continue
        if f._field_type is _FIELD_INITVAR and f.default is MISSING:
            raise TypeError(f'InitVar {f.name!r} must be specified with replace()')
        changes[f.name] = getattr(self, f.name)
    return self.__class__(**changes)

# WARNING: Decompyle incomplete
