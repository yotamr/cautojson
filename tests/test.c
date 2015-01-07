#include "test_header_auto.h"
#include "CUnit/Basic.h"
#include "CUnit/Console.h"
#include "CUnit/Automated.h"
#include "CUnit/CUCurses.h"
#include <assert.h>
#include <string.h>

#define ADD_TEST(name, func) assert(NULL != CU_add_test(suite, name, func))

#define ARRAY_LENGTH(x) (sizeof(x) / sizeof(x[0]))
int init_suite_success(void) { return 0; }
int init_suite_failure(void) { return -1; }
int clean_suite_success(void) { return 0; }
int clean_suite_failure(void) { return -1; }

static void register_suite(CU_pSuite *suite, const char *name)
{
   /* add a suite to the registry */
    (*suite) = CU_add_suite(name, init_suite_success, clean_suite_success);
    assert(NULL != *suite);
}

void scalars(void)
{
    struct scalars s = {.a = 500,
                        .e = ENUM_VAL_2,
                        .string = {"hello"}};
    struct scalars s_from_json;

    json_t *json = scalars_to_json(&s);
    CU_ASSERT(0 == scalars_from_json(json, &s_from_json));
    CU_ASSERT(500 == s_from_json.a);
    CU_ASSERT(ENUM_VAL_2 == s_from_json.e);
    CU_ASSERT(strcmp(s.string, s_from_json.string) == 0);
}

void generate_scalars(struct scalars *s, unsigned int count, struct scalars *base)
{
    unsigned int i;
    int a = 300;
    enum some_enum e = 0;

    base->a = a;
    base->e = e;
    char str[500] = "hello";
    strcpy(base->string, str);
    for (i = 0; i < count; i++) {
        s->a = a;
        s->e = e;
        strcpy(s->string, str);
        a += 1;
        e += 1;
        s++;
    }
}
void var_lists(void)
{
    struct scalars ss[3];
    struct scalars *scalar_ptrs[] = {&ss[0], &ss[1], &ss[2], NULL};
    struct scalars base;
    struct var_list v;
    struct var_list v_from_json;

    v.i = 500;
    v.s = scalar_ptrs;
    generate_scalars(ss, ARRAY_LENGTH(ss), &base);
    json_t *json;
    json = var_list_to_json(&v);
    CU_ASSERT(NULL != json);
    int rc = var_list_from_json(json, &v_from_json);
    CU_ASSERT(0 == rc);
    unsigned int i;
    for (i = 0; v_from_json.s[i] != NULL; i++) {
        CU_ASSERT(base.a == v_from_json.s[i]->a);
        CU_ASSERT(base.e == v_from_json.s[i]->e);
        CU_ASSERT(strcmp(base.string, v_from_json.s[i]->string) == 0);
        base.a += 1;
        base.e += 1;
    }

    CU_ASSERT(i == ARRAY_LENGTH(ss));
}

#define NESTED_COUNT (3)
#define BASE_INTEGER 100
void nested_var_list(void)
{
    struct scalars base;
    struct scalars ss[2 * NESTED_COUNT];
    struct scalars *scalar_ptrs[NESTED_COUNT][3] = {{&ss[0], &ss[1], NULL},
                                                    {&ss[2], &ss[3], NULL},
                                                    {&ss[4], &ss[5], NULL}};
    generate_scalars(ss, ARRAY_LENGTH(ss), &base);
    struct var_list vars[] = {
        {.i = BASE_INTEGER, .s = scalar_ptrs[0]},
        {.i = BASE_INTEGER + 1, .s = scalar_ptrs[1]},
        {.i = BASE_INTEGER + 2, .s = scalar_ptrs[2]}
    };

    struct var_list *var_list_ptrs[ARRAY_LENGTH(vars) + 1];
    for (int i = 0; i < ARRAY_LENGTH(vars); i++) {
        var_list_ptrs[i] = &vars[i];
    }

    var_list_ptrs[ARRAY_LENGTH(var_list_ptrs) - 1] = NULL;

    struct nested_var_list nested = {
        .s = var_list_ptrs,
        .a = BASE_INTEGER
    };

    json_t *json = nested_var_list_to_json(&nested);
    struct nested_var_list nested_from_json;
    int rc = nested_var_list_from_json(json, &nested_from_json);
    CU_ASSERT(0 == rc);
    int i;
    int j;
    for (i = 0; nested_from_json.s[i] != NULL; i++) {
        for (j = 0; nested_from_json.s[i]->s[j] != NULL; j++) {
            CU_ASSERT(nested_from_json.s[i]->s[j]->a == base.a + (i * 2)  + j);
        }

        CU_ASSERT(j == 2);
    }

    CU_ASSERT(i == ARRAY_LENGTH(var_list_ptrs) - 1);
    nested_var_list_free(&nested_from_json);
}

#define VAR_STRING "bla bla boy asfslkdafjasfdlkj asfdalkfdsj pwqerrwgf0"
void var_string(void)
{
    struct var_string s = {.a = 300,
                           .s = "hello"};

    struct var_string s_from_json;
    json_t *json = var_string_to_json(&s);
    int rc = var_string_from_json(json, &s_from_json);
    CU_ASSERT(0 == rc);
    CU_ASSERT(s.a == s_from_json.a);
    CU_ASSERT(strcmp(s.s, s_from_json.s) == 0);
    var_string_free(&s_from_json);
}

void register_tests(CU_pSuite suite)
{
    ADD_TEST("scalars", scalars);
    ADD_TEST("var_lists", var_lists);
    ADD_TEST("var_string", var_string);
    ADD_TEST("nested_var_list", nested_var_list);
}

int main(int argc, char **argv)
{
    if (CUE_SUCCESS != CU_initialize_registry())
      return CU_get_error();

    CU_pSuite suite = NULL;
    register_suite(&suite, "suite");
    register_tests(suite);

    /* Run all tests using the basic interface */
   CU_basic_set_mode(CU_BRM_VERBOSE);
   CU_basic_run_tests();
   printf("\n");
   CU_basic_show_failures(CU_get_failure_list());
   printf("\n\n");
}
