TEST_FILES=tests/test.c
TEST_HEADER=tests/test_header.h
test: autojson.py tests/test.c tests/test_header.h
	python autojson.py tests/test_header.h tests/test_header_auto.h tests/test_header_auto.c 
	gcc -g --std=gnu99 -I. -Itests tests/test_header_auto.c tests/test.c -lcunit -ljansson -o tests/test

