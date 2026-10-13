# Toolchain file for avr-gcc. Override the compiler location with
#   -DAVR_TOOLCHAIN_DIR=/path/to/avr-gcc/bin
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR avr)

set(AVR_TOOLCHAIN_DIR "" CACHE PATH "Directory with avr-gcc binaries (empty = PATH)")
if(AVR_TOOLCHAIN_DIR)
	set(_p "${AVR_TOOLCHAIN_DIR}/")
endif()

set(CMAKE_C_COMPILER   ${_p}avr-gcc)
set(CMAKE_CXX_COMPILER ${_p}avr-g++)
set(CMAKE_ASM_COMPILER ${_p}avr-gcc)
set(AVR_OBJCOPY        ${_p}avr-objcopy)
set(AVR_OBJDUMP        ${_p}avr-objdump)
set(AVR_SIZE           ${_p}avr-size)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
