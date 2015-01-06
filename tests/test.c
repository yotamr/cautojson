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

void register_tests(CU_pSuite suite)
{
    ADD_TEST("scalars", scalars);
    ADD_TEST("var_lists", var_lists);
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
