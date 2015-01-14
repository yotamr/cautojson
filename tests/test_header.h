#pragma once

#include "../autojson.h"

enum some_enum {
    ENUM_VAL_1,
    ENUM_VAL_2,
};

struct scalars {
    int a;
    enum some_enum e;
    char string[500];
    long long l;
    JSONABLE;
};

struct var_list {
    int i;
    struct scalars **s;
    JSONABLE;
};

struct var_string {
    int a;
    char *s;
    JSONABLE;
};

struct nested_var_list {
    struct var_list **s;
    int a;
    JSONABLE;
};
