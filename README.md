# Introduction

cautojson is a Python script that takes in as input a series of C
header files and automatically creates bindings that serialize and
parse such structres using JSON.

cautojson currently uses jansoon for serialization and parsing of
json.

The motivation behind this project is to reduce the amount of
boilerplate code that normally needs writing when working with C and
json.

Note that in its current form, cautojson is more of a clever hack than
a complete and polished product. This is a work in progress.

# Quick start

Consider the following C structure
```c

#ifndef __EXAMPLE_H__
#define __EXAMPLE_H__

#include "autojson.h"

typedef enum my_enum { FOO, BAR, BAZ};

struct struct_c {
    char bla[50];
    JSONABLE;
};

struct struct_b {
    int int_member;
    struct struct_c c;
    JSONABLE;
};
struct struct_a {
    int int_member;
    char string_member[50];
    struct struct_b b;
    enum my_enum e;
    JSONABLE;
};


#endif

```

To use these structures with JSON, a developer is required to manually write
repetitive code that does the parsing/serialization. In order to indicate to cautojson that
bindings should be created for a given structure, a JSONABLE magical
member is declared in the structure. Note that nested structures
referenced by the top-most structure (struct_a), must also be marked
as JSONABLE. Other than the marking of the structure as jsonable, no
other special action is required by the developer.

To generate bindings from the provided `example.h`, we run `cautojson.py example.h
example_json_bindings.c example_json_bindings.h`. cautojson generates
complete and compilable code. Let's take a look at the
generated header file `example_json_bindings.h`

```c
#ifndef __EXAMPLE_H_JSON_AUTO__
#define __EXAMPLE_H_JSON_AUTO__
#include <jansson.h>
#include <string.h>
#include "example.h"

json_t *struct_b_to_json(const struct struct_b *this);
int struct_b_from_json(json_t *json, struct struct_b *out);

json_t *struct_c_to_json(const struct struct_c *this);
int struct_c_from_json(json_t *json, struct struct_c *out);

json_t *struct_a_to_json(const struct struct_a *this);
int struct_a_from_json(json_t *json, struct struct_a *out);
#endif /* __EXAMPLE_H_JSON_AUTO__ */

```

cautojson generated function headers for each jsonable structure. Each
structure has a to and from methods.

Let's take a look at the generated C file
```c

#include "example.h"
#include "e.h"
json_t *struct_b_to_json(const struct struct_b *this)
{
	json_t *obj = json_object();
	json_object_set(obj, "int_member", json_integer(this->int_member));
	json_object_set(obj, "c", struct_c_to_json(&this->c));
	return obj;
}
int struct_b_from_json(json_t *json, struct struct_b *out)
{
	char *outCRAZYBASTARDcCRIMINALTRICKERbla = NULL;
	int rc = json_unpack(json, "{s:i,s:{s:s}, }", "int_member", &out->int_member, "c", "bla", &outCRAZYBASTARDcCRIMINALTRICKERbla);
	if (0 != rc) { return rc;};
	strncpy(out->c.bla, outCRAZYBASTARDcCRIMINALTRICKERbla, 49);
	return 0;
}
json_t *struct_c_to_json(const struct struct_c *this)
{
	json_t *obj = json_object();
	json_object_set(obj, "bla", json_string(this->bla));
	return obj;
}
int struct_c_from_json(json_t *json, struct struct_c *out)
{
	char *outCRAZYBASTARDbla = NULL;
	int rc = json_unpack(json, "{s:s}", "bla", &outCRAZYBASTARDbla);
	if (0 != rc) { return rc;};
	strncpy(out->bla, outCRAZYBASTARDbla, 49);
	return 0;
}
json_t *struct_a_to_json(const struct struct_a *this)
{
	json_t *obj = json_object();
	json_object_set(obj, "int_member", json_integer(this->int_member));
	json_object_set(obj, "string_member", json_string(this->string_member));
	json_object_set(obj, "b", struct_b_to_json(&this->b));
	json_object_set(obj, "e", json_integer(this->e));
	return obj;
}
int struct_a_from_json(json_t *json, struct struct_a *out)
{
	char *outCRAZYBASTARDstring_member = NULL;
	char *outCRAZYBASTARDbCRIMINALTRICKERcCRIMINALTRICKERbla = NULL;
	int rc = json_unpack(json, "{s:i,s:s,s:{s:i,s:{s:s}, }, s:i}", "int_member", &out->int_member, "string_member", &outCRAZYBASTARDstring_member, "b", "int_member", &out->b.int_member, "c", "bla", &outCRAZYBASTARDbCRIMINALTRICKERcCRIMINALTRICKERbla, "e", &out->e);
	if (0 != rc) { return rc;};
	strncpy(out->string_member, outCRAZYBASTARDstring_member, 49);
	strncpy(out->b.c.bla, outCRAZYBASTARDbCRIMINALTRICKERcCRIMINALTRICKERbla, 49);
	return 0;
}
```

# Features

1. Supported C types: char-arrays, ints, enums and structures
2. Allows control over which members are serialized using the `///<
   noserialize` special comment
3. When generating bindings for a given .h file, only generate code
   for the struct declarations in that particular file
4. Uses libclang to semantically analyze provided source-code
5. Generates complete and compilable code

# TODO
1. Refactor the code, it got very messy :)
2. Get rid of the `///>` notation in favor of a more declarative macro
3. Add some more examples and testers
4. Add support for json/c arrays
5. Integrate with pip
6. Clearer error messages

# Thanks
1. Thanks to Tomer Filiba for clike.py, which provides a nice
   contextmanager based approach to code generation
2. Kudos to the jansson team for creating a well thought-out and
   straightforward lib
