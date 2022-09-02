cmake_minimum_required(VERSION 3.20)
project(cgi C)
set(CMAKE_C_STANDARD 11)

add_executable(env env.c)
set_target_properties(env PROPERTIES SUFFIX .cgi)