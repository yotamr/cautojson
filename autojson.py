#!/usr/bin/python

##############################################################################
#
# Copyright 2014, Yotam Rubin <yotam@wizery.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##############################################################################

import sys
from clang import cindex
from clang.cindex import CursorKind as ck
from clang.cindex import TypeKind as tk
from IPython import embed
from clike import *
import click
import os
from collections import namedtuple

CleanupInfo = namedtuple('CleanupInfo', ['expression', 'label'])

class CantSerializeUnion(Exception):
    pass

class CantSerializeAnonymousStruct(Exception):
    pass

class StructNotJsonable(Exception):
    pass

class CantManglePtr(Exception):
    pass

class CantSerializeConstantArray(Exception):
    pass

class CantSerializeField(Exception):
    pass

class CantParseField(Exception):
    pass

class CantParse(Exception):
    pass

def _is_struct_jsonable(sd):
    for field in sd.get_children():
        if field.kind != ck.FIELD_DECL:
            continue

        if field.displayname == '__jsonable':
            return True

    return False

struct_jsonable = _is_struct_jsonable

def _is_var_array(t):
    t = t.get_canonical()
    if t.kind != tk.POINTER:
        return False

    if t.get_pointee().kind != tk.POINTER:
        return False

    pointee = t.get_pointee().get_pointee()
    if pointee.kind != tk.RECORD:
        return False

    sd = pointee.get_declaration()
    return _is_struct_jsonable(sd)

def _is_static_string(t):
    return (t.kind == tk.CONSTANTARRAY and
    t.get_array_element_type().kind == tk.CHAR_S)

def _is_var_string(t):
    t = t.get_canonical()
    if t.kind != tk.POINTER:
        return False

    return t.get_pointee().kind == tk.CHAR_S

def _get_jsonable_structs(root, h_file):
    jsonables = {}
    filename = root.translation_unit.spelling
    def aux(node):
        if _is_struct_jsonable(node):
            jsonables[node.spelling] = node

        for node in node.get_children():
            aux(node)

        return jsonables

    return aux(root)


def _validate_struct_decl(sd):
    if sd.type.get_canonical().get_declaration().kind == ck.UNION_DECL:
        raise CantSerializeUnion(sd)

    if not sd.spelling:
        raise CantSerializeAnonymousStruct(sd.type.get_canonical().spelling)

    if not _is_struct_jsonable(sd):
        raise StructNotJsonable(sd.spelling)


def struct_serializer_function_name(sd):
    sd = sd.type.get_canonical().get_declaration()
    _validate_struct_decl(sd)
    return '{0}_to_json'.format(sd.spelling)

def struct_free_function_name(sd):
    sd = sd.type.get_canonical().get_declaration()
    _validate_struct_decl(sd)
    return '{0}_free'.format(sd.spelling)

def struct_parser_function_name(sd):
    sd = sd.type.get_canonical().get_declaration()
    _validate_struct_decl(sd)
    return '{0}_from_json'.format(sd.spelling)

def _ignore_field(f):
    if f.brief_comment == 'noserialize' or f.spelling == '__jsonable':
        return True
    else:
        return False

def _serialize_record_array(s, sd, full_field_name, loop_fmt, lvalue_modifier, mod):
    BLOCK = mod.block
    STMT = mod.stmt
    array_name = _mangle_ptr(full_field_name) + "_array"
    STMT('json_t *{0} = json_array()'.format(array_name))
    struct_serializer_func = struct_serializer_function_name(sd.get_declaration())
    with BLOCK(loop_fmt.format(full_field_name)):
        STMT('json_array_append_new({0}, {1}({2}{3}[i]))'.format(array_name,
                                                             struct_serializer_func,
                                                             lvalue_modifier,
                                                             full_field_name))

    return array_name

def _serialize_string(s, ct, full_field_name, mod):
    return "json_string({0})".format(full_field_name)

def _serialize_record_static_array(s, ct, full_field_name, mod):
    loop_fmt = 'for (int i = 0; i < sizeof({0}) / sizeof({0}[0]); i++)'
    return _serialize_record_array(s, ct.get_array_element_type().get_canonical(), full_field_name, loop_fmt, '&', mod)

def _serialize_record_var_array(s, ct, full_field_name, mod):
    loop_fmt = 'for (int i = 0; {0}[i] != 0; i++)'
    return _serialize_record_array(s, ct.get_pointee().get_pointee(), full_field_name, loop_fmt, '', mod)


def _handle_array_serialization(s, ct, full_field_name, mod):
    element_type_kind = ct.get_array_element_type().kind
    if not element_type_kind in [tk.CHAR_S, tk.RECORD]:
        raise CantSerializeConstantArray(s.displayname)

    if element_type_kind == tk.RECORD:
        raise NotImplemented()
    elif element_type_kind == tk.CHAR_S:
        return _serialize_string(s, ct, full_field_name, mod)

def recursively__generate_serializer(s, mod):
    BLOCK = mod.block
    STMT = mod.stmt
    DOC = mod.doc
    SEP = mod.sep

    if s.kind == ck.STRUCT_DECL:
        STMT("json_t *obj = json_object()")
        fields = [f
                  for f in s.get_children()
                  if f.kind == ck.FIELD_DECL]

        for f in fields:
            if _ignore_field(f):
                continue
            recursively__generate_serializer(f, mod)

        STMT("return obj")

    if s.kind == ck.FIELD_DECL:
        ct = s.type.get_canonical()
        full_field_name = "this->{0}".format(s.spelling)
        if ct.kind == tk.RECORD:
            sd = ct.get_declaration()
            field_value = '{0}(&{1})'.format(struct_serializer_function_name(sd), full_field_name)
        elif ct.kind == tk.INT or ct.kind == tk.ENUM:
            field_value = "json_integer({0})".format(full_field_name)
        elif ct.kind == tk.CONSTANTARRAY:
            field_value = _handle_array_serialization(s, ct, full_field_name, mod)
        elif _is_var_array(ct):
            field_value = _serialize_record_var_array(s, ct, full_field_name, mod)
        elif _is_var_string(ct):
            field_value = _serialize_string(s, ct, full_field_name, mod)
        else:
            raise CantSerializeField(s.displayname, ct.kind)

        STMT('json_object_set(obj, "{0}", {1})', s.displayname, field_value)

def _quote(s):
    return '"{0}"'.format(s)

def _normalize_typename(typename):
    typename = typename.replace('*', 'pointer')
    return typename.translate(None, ' []')

def _normalize_labelname(var):
    return var.replace('->', '_').replace('.', '_')

def _mangle_ptr(ptr):
    if 'CRAZYBASTARD' in ptr or 'CRIMINALTRICKER' in ptr:
        raise CantManglePtr(ptr)

    return ptr.replace('->', 'CRAZYBASTARD').replace('.', 'CRIMINALTRICKER')

def _demangle_ptr(ptr):
    return ptr.replace('CRAZYBASTARD', '->').replace('CRIMINALTRICKER', '.')

def recursively__generate_struct_parser(s, mod, out, unpack, add_ptr, add_array):
        unpack("{")
        fields = [f
                  for f in s.get_children()
                  if f.kind == ck.FIELD_DECL]

        for f in fields:
            if _ignore_field(f):
                continue

            recursively__generate_parser(f, mod, out, unpack, add_ptr, add_array)
        unpack("}")

def recursively__generate_field_parser(s, mod, out, unpack, add_ptr, add_array):
    STMT = mod.stmt
    BLOCK = mod.block

    def ptr(field_name):
        return '&' + field_name

    ct = s.type.get_canonical()
    full_field_name = "{0}{1}".format(out, s.spelling)
    _quoted_field_name = _quote(s.spelling)
    if ct.kind == tk.RECORD:
        sd = ct.get_declaration()
        unpack("s:", _quoted_field_name)
        recursively__generate_parser(sd, mod, full_field_name + ".", unpack, add_ptr, add_array)
        unpack(", ")
    elif ct.kind == tk.INT or ct.kind == tk.ENUM:
        unpack("s:i,", _quoted_field_name, ptr(full_field_name))
    elif _is_var_string(ct) or _is_static_string(ct):
        is_var = _is_var_string(ct)
        tmp_ptr = _mangle_ptr(full_field_name)
        STMT('char *{0} = NULL'.format(tmp_ptr))
        add_ptr(tmp_ptr, ct.get_array_size(), is_var)
        unpack("s:s,", _quoted_field_name, ptr(tmp_ptr))
    elif (ct.kind == tk.CONSTANTARRAY and
          ct.get_array_element_type().get_canonical().kind == tk.RECORD):
        raise NotImplemented()
        # tmp_json_obj = _mangle_ptr(full_field_name)
        # unpack("s:[{0}]", _quoted_field_name, ptr(tmp_json_obj))
        # add_array(tmp_json_obj, ct)
    elif _is_var_array(ct):
        #raise NotImplemented()
        tmp_json_obj = _mangle_ptr(full_field_name)
        STMT('json_t *{0} = NULL'.format(tmp_json_obj))
        unpack("s:o", _quoted_field_name, ptr(tmp_json_obj))
        add_array(tmp_json_obj, ct)
    else:
        raise CantParseField(s.spelling)


def recursively__generate_parser(s, mod, out, unpack, add_ptr, add_array):
    if s.kind == ck.STRUCT_DECL:
        return recursively__generate_struct_parser(s, mod, out, unpack, add_ptr, add_array)

    if s.kind == ck.FIELD_DECL:
        return recursively__generate_field_parser(s, mod, out, unpack, add_ptr, add_array)

    raise CantParse(s.spelling)

def _safe_allocation(stmt, allocated_type, allocated_ptr, allocation_size, cleanups, create_local_var = True):
    base_fmt = '{1} = ({0})malloc({2})'
    if create_local_var:
        fmt = '{0} ' + base_fmt
    else:
        fmt = base_fmt;
    stmt(fmt.format(allocated_type, allocated_ptr, allocation_size))
    if not cleanups:
        goto_expr = 'goto exit'
    else:
        goto_expr = 'goto ' + cleanups[-1].label
    stmt('if (NULL == {0}) {1}'.format(allocated_ptr, goto_expr))
    cleanups.append(
        CleanupInfo('free({0})'.format(allocated_ptr),
                    _normalize_labelname(allocated_ptr + '_cleanup')))

def _generate_cleanups(stmt, block, cleanups):
    if not cleanups:
        return

    del cleanups[-1]
    for cleanup in cleanups[::-1]:
        stmt(cleanup.label + ':', suffix = '')
        stmt(cleanup.expression)

def _generate_var_array_parser(C_STMT, C_BLOCK, arrays, cleanups):
    for array_ptr, array_type in arrays:
        array_ptr_size = array_ptr + '_size'
        array_ptr_buffer = array_ptr + '_buffer'
        struct_type = array_type.get_pointee().get_pointee().spelling
        struct_decl = array_type.get_pointee().get_pointee().get_declaration()
        with C_BLOCK('if (!json_is_array({0}))'.format(array_ptr)):
            C_STMT('return -1');

        ptr = _demangle_ptr(array_ptr)
        C_STMT('int {0} = json_array_size({1})'.format(array_ptr_size, array_ptr))
        _safe_allocation(C_STMT, struct_type + '*', array_ptr_buffer,
                         'sizeof({0}) * {1}'.format(struct_type, array_ptr_size), cleanups,
                         create_local_var = True)
        _safe_allocation(C_STMT, struct_type + '**', ptr, 'sizeof(intptr_t) * {0} + 1'.format(array_ptr_size),
                         cleanups, create_local_var = False)
        with C_BLOCK('for (int i = 0; i < {0}; i++)'.format(array_ptr_size)):
            C_STMT('rc = {0}(json_array_get({1}, i), &{2}[i])'.format(struct_parser_function_name(struct_decl),
                                                                      array_ptr, array_ptr_buffer))
            with C_BLOCK('if (0 != rc)'):
                C_STMT('goto {0}'.format(cleanups[0].label))

            C_STMT('{0}[i] = &{1}[i]'.format(ptr, array_ptr_buffer))

        C_STMT('{0}[{1}] = NULL'.format(ptr, array_ptr_size))

    C_STMT('goto exit');
    _generate_cleanups(C_STMT, C_BLOCK, cleanups)


def _generate_free_implementation(s, h_module, C_BLOCK, C_STMT, function_name):
    fields = [f
              for f in s.get_children()
              if f.kind == ck.FIELD_DECL]

    with C_BLOCK(function_name):
        for f in fields:
            if _is_var_string(f.type.get_canonical()):
                C_STMT('free(this->{0})'.format(f.displayname))
            if f.type.get_canonical().kind == tk.RECORD and _is_struct_jsonable(f.type.get_canonical().get_declaration()):
                C_STMT('{0}(&this->{1})'.format(struct_free_function_name(f), f.displayname))
            if _is_var_array(f.type.get_canonical()):
                sd = f.type.get_canonical().get_pointee().get_pointee().get_declaration()
                with C_BLOCK('for (int ___i = 0; this->{0}[___i] != NULL; ___i++)'.format(f.displayname)):
                    C_STMT('{0}(this->{1}[___i])'.format(struct_free_function_name(sd), f.displayname))

                C_STMT('free(*this->{0})'.format(f.displayname))
                C_STMT('free(this->{0})'.format(f.displayname))



def _generate_parser(main_filename, s, c_module, h_module):
    function_name = 'int {0}(json_t *json, struct {1} *out)'.format(struct_parser_function_name(s),
                                                                    s.displayname)
    free_function_name = 'void {0}(struct {1} *this)'.format(struct_free_function_name(s),
                                                             s.displayname)


    C_STMT = c_module.stmt
    C_BLOCK = c_module.block

    h_module.stmt(function_name)
    h_module.stmt(free_function_name)
    if s.location.file.name != main_filename:
        return

    with C_BLOCK(function_name):
        unpack_str = []
        destinations = []
        str_ptrs = []
        arrays = []
        cleanups = []
        def unpack(fmt, *to):
            unpack_str.append(fmt)
            destinations.extend(list(to))

        def add_array(array_json_name, array_type):
            arrays.append((array_json_name, array_type))

        def add_ptr(ptr_name, buffer_size, is_var):
            str_ptrs.append((ptr_name, buffer_size, is_var))

        recursively__generate_parser(s, c_module, "out->", unpack, add_ptr, add_array)
        function_body = 'json_unpack(json, {0}, {1})'.format('"' + ''.join(unpack_str).replace(",}","}") + '"'
                                                            , ', '.join(destinations))
        C_STMT("int rc = {0}".format(function_body))
        C_STMT('if (0 != rc) { return rc;}')
        for str_ptr, buffer_size, is_var in str_ptrs:
            ptr = _demangle_ptr(str_ptr)
            if is_var:
                C_STMT('{0} = strdup({1})'.format(ptr, str_ptr))
            else:
                C_STMT('strncpy({0}, {1}, {2})'.format(ptr, str_ptr, buffer_size - 1))

        _generate_var_array_parser(C_STMT, C_BLOCK, arrays, cleanups)
        C_STMT('exit:', suffix = '')
        C_STMT('return rc')

    _generate_free_implementation(s, h_module, C_BLOCK, C_STMT, free_function_name)


def _generate_serializer(main_filename, s, c_module, h_module):
    function_name = 'json_t *{0}(const struct {1} *this)'.format(struct_serializer_function_name(s),
                                                                  s.displayname)
    h_module.stmt("{0}", function_name)
    if s.location.file.name != main_filename:
        return

    with c_module.block(function_name):
        recursively__generate_serializer(s, c_module)


def _add_include(module, filename):
    module.stmt('#include {0}'.format(filename), suffix = '')

def _add_base_includes(module):
    includes = ["<jansson.h>",
                "<string.h>",
                "<stdint.h>"]

    module.stmt('char *strdup(const char *s)')
    for include in includes:
        _add_include(module, include)

def _init_h_module(input, h_file):
    m = Module()
    h_name = '__{0}_JSON_AUTO__'.format(os.path.basename(input).replace('.', '_').upper())
    m.stmt('#ifndef {0}'.format(h_name), suffix = '')
    m.stmt('#define {0}'.format(h_name), suffix = '')
    _add_base_includes(m)
    _add_include(m, _quote(input))


    return m, h_name

def _fini_h_module(m, h_name):
    m.stmt('#endif /* {0} */'.format(h_name), suffix = '')


def _init_c_module(input, h_output):
    m = Module()
    m.stmt('#include "{0}"'.format(input), suffix = '')
    m.stmt('#include "{0}"'.format(h_output), suffix = '')
    _add_base_includes(m)

    return m

def _generate_code(input, c_module, h_module):
    i = cindex.Index.create()
    t = i.parse(input, args = ["-C"])
    main_filename = t.spelling

    for struct in _get_jsonable_structs(t.cursor, input).itervalues():
        _generate_serializer(main_filename, struct, c_module, h_module)
        _generate_parser(main_filename, struct, c_module, h_module)

@click.command()
@click.argument('input', type=click.Path())
@click.argument('h_output')
@click.argument('c_output')
@click.option('--interface-only', default=False, is_flag=True)
def generate_code(interface_only, input, h_output, c_output):
    c_module = _init_c_module(input, h_output)
    h_module, h_name = _init_h_module(input, h_output)
    _generate_code(input, c_module, h_module)

    _fini_h_module(h_module, h_name)
    if not interface_only:
        file(c_output, "wb").write(c_module.render())

    file(h_output, "wb").write(h_module.render())

if __name__ == '__main__':
    generate_code()
