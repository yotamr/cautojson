##############################################################################
#
# Copyright 2011, Yotam Rubin <yotamrubin@gmail.com>
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

class CantSerializeUnion(Exception):
    pass

class CantSerializeAnonymousStruct(Exception):
    pass

class StructNotJsonable(Exception):
    pass

class CantManglePtr(Exception):
    pass


def _is_struct_jsonable(sd):
    for field in sd.get_children():
        if field.kind != ck.FIELD_DECL:
            continue

        if field.displayname == '__jsonable':
            return True

    return False

def _get_jsonable_structs(root):
    jsonables = {}
    def aux(node):
        def json_packable_struct(node):
            if node.kind != ck.STRUCT_DECL:
                return

        if _is_struct_jsonable(node):
            jsonables[node.spelling] = node

        json_packable_struct(node)
        for node in node.get_children():
            aux(node)


        return jsonables

    return aux(root)


def _validate_struct_decl(sd):
    if sd.type.get_declaration().kind == ck.UNION_DECL:
        raise CantSerializeUnion(sd)

    if not sd.spelling:
        raise CantSerializeAnonymousStruct(sd.type.spelling)

    if not _is_struct_jsonable(sd):
        raise StructNotJsonable(sd.spelling)


def struct_serializer_function_name(sd):
    _validate_struct_decl(sd)
    return '{0}_to_json'.format(sd.spelling)

def struct_parser_function_name(sd):
    _validate_struct_decl(sd)
    return '{0}_from_json'.format(sd.spelling)

def _ignore_field(f):
    if f.brief_comment == 'noserialize' or f.spelling == '__jsonable':
        return True
    else:
        return False

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
            recursively__generate_serializer(f, mod);

        STMT("return obj");

    if s.kind == ck.FIELD_DECL:
        ct = s.type.get_canonical()
        full_field_name = "this->{0}".format(s.spelling)
        if ct.kind == tk.RECORD:
            sd = ct.get_declaration()
            field_value = '{0}(&{1})'.format(struct_serializer_function_name(sd), full_field_name)
        elif ct.kind == tk.INT or ct.kind == tk.ENUM:
            field_value = "json_integer({0})".format(full_field_name)
        elif (ct.kind == tk.CONSTANTARRAY and
              ct.get_array_element_type().kind == tk.CHAR_S):
            field_value = "json_string({0})".format(full_field_name)
        else:
            embed()

        STMT('json_object_set(obj, "{0}", {1})', s.displayname, field_value)

def _quote(s):
    return '"{0}"'.format(s)

def _mangle_ptr(ptr):
    if 'CRAZYBASTARD' in ptr or 'CRIMINALTRICKER' in ptr:
        raise CantManglePtr(ptr)

    return ptr.replace('->', 'CRAZYBASTARD').replace('.', 'CRIMINALTRICKER')

def _demangle_ptr(ptr):
    return ptr.replace('CRAZYBASTARD', '->').replace('CRIMINALTRICKER', '.')

def recursively__generate_parser(s, mod, out, unpack, ptrs):
    BLOCK = mod.block
    STMT = mod.stmt
    DOC = mod.doc
    SEP = mod.sep

    def ptr(field_name):
        return '&' + field_name

    if s.kind == ck.STRUCT_DECL:
        unpack("{")
        fields = [f
                  for f in s.get_children()
                  if f.kind == ck.FIELD_DECL]

        for f in fields:
            if _ignore_field(f):
                continue

            recursively__generate_parser(f, mod, out, unpack, ptrs);
        unpack("}")

    if s.kind == ck.FIELD_DECL:
        ct = s.type.get_canonical()
        full_field_name = "{0}{1}".format(out, s.spelling)
        _quoted_field_name = _quote(s.spelling)
        if ct.kind == tk.RECORD:
            sd = ct.get_declaration()
            unpack("s:", _quoted_field_name)
            recursively__generate_parser(sd, mod, full_field_name + ".", unpack, ptrs)
            unpack(", ")
        elif ct.kind == tk.INT or ct.kind == tk.ENUM:
            unpack("s:i,", _quoted_field_name, ptr(full_field_name))
        elif (ct.kind == tk.CONSTANTARRAY and
              ct.get_array_element_type().kind == tk.CHAR_S):
            tmp_ptr = _mangle_ptr(full_field_name);
            STMT('char *{0} = NULL;'.format(tmp_ptr))
            ptrs(tmp_ptr, ct.get_array_size())
            unpack("s:s,", _quoted_field_name, ptr(tmp_ptr))
        else:
            embed()

def _generate_parser(s, c_module, h_module):
    function_name = 'int {0}(json_t *json, struct {1} *out)'.format(struct_parser_function_name(s),
                                                                    s.displayname)

    h_module.stmt(function_name);
    with c_module.block(function_name):
        unpack_str = []
        destinations = []
        tmp_str_ptrs = []
        def unpack(fmt, *to):
            unpack_str.append(fmt)
            destinations.extend(list(to))

        def ptrs(ptr_name, buffer_size):
            tmp_str_ptrs.append((ptr_name, buffer_size))

        recursively__generate_parser(s, c_module, "out->", unpack, ptrs)
        function_body = 'json_unpack(json, {0}, {1})'.format('"' + ''.join(unpack_str).replace(",}","}") + '"'
                                                            , ', '.join(destinations))
        c_module.stmt("int rc = {0}".format(function_body))
        c_module.stmt('if (0 != rc) { return rc;}')
        for tmp_str_ptr, buffer_size in tmp_str_ptrs:
            ptr = _demangle_ptr(tmp_str_ptr)
            c_module.stmt('strncpy({0}, {1}, {2});'.format(ptr, tmp_str_ptr, buffer_size - 1))

        c_module.stmt('return 0');


def _generate_serializer(s, c_module, h_module):
    function_name = 'json_t *{0}(const struct {1} *this)'.format(struct_serializer_function_name(s),
                                                                  s.displayname)
    h_module.stmt("{0}", function_name)
    with c_module.block(function_name):
        recursively__generate_serializer(s, c_module)





def _init_h_module(input, h_file):
    m = Module()
    h_name = '__{0}_JSON_AUTO__'.format(os.path.basename(input).replace('.', '_').upper())
    m.stmt('#ifndef {0}'.format(h_name), suffix = '')
    m.stmt('#define {0}'.format(h_name), suffix = '')
    includes = ["<jansson.h>",
                "<string.h>",
                _quote(input)]

    for include in includes:
        m.stmt('#include {0}'.format(include), suffix = '')

    return m, h_name

def _fini_h_module(m, h_name):
    m.stmt('#endif /* {0} */'.format(h_name), suffix = '')


def _init_c_module(input, h_output):
    m = Module()
    m.stmt('#include "{0}"'.format(input), suffix = '')
    m.stmt('#include "{0}"'.format(h_output), suffix = '')

    return m

def _generate_code(input, c_module, h_module):
    i = cindex.Index.create()
    t = i.parse(input, args = ["-C"])

    for struct in _get_jsonable_structs(t.cursor).itervalues():
        _generate_serializer(struct, c_module, h_module)
        _generate_parser(struct, c_module, h_module)

@click.command()
@click.argument('input', type=click.Path())
@click.argument('h_output')
@click.argument('c_output')
def generate_code(input, h_output, c_output):

    c_module = _init_c_module(input, h_output)
    h_module, h_name = _init_h_module(input, h_output)
    _generate_code(input, c_module, h_module)

    _fini_h_module(h_module, h_name)
    file(c_output, "wb").write(c_module.render())
    file(h_output, "wb").write(h_module.render())

if __name__ == '__main__':
    generate_code()
