cmake_minimum_required(VERSION 3.13)

if(NOT CMAKE_TOOLCHAIN_FILE)
	set(CMAKE_TOOLCHAIN_FILE ${CMAKE_CURRENT_SOURCE_DIR}/cmake/avr-gcc.cmake)
endif()

project(midi2aux CXX)

set(MCU        atmega328p)
set(F_CPU      16000000L)
set(AVR_PORT   /dev/ttyUSB0 CACHE STRING "Serial port for avrdude upload")
set(AVR_BAUD   57600        CACHE STRING "Bootloader baud rate (old Nano bootloader: 57600)")

# Polyphonic build parameters (target midi2aux_poly)
set(POLY_VOICES   4     CACHE STRING "Number of voices")
set(POLY_FS       31250 CACHE STRING "Sample rate, Hz")
set(POLY_PWM_TOP  255   CACHE STRING "Timer2 TOP (255 = 62.5 kHz, 99 = 160 kHz)")
set(POLY_ACC_BITS 24    CACHE STRING "Phase accumulator width (16 or 24)")

file(GLOB SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/fw/src/*.cpp)

function(avr_firmware name)
	add_executable(${name} ${SOURCES})
	set_target_properties(${name} PROPERTIES SUFFIX .elf)
	target_compile_definitions(${name} PRIVATE F_CPU=${F_CPU} ${ARGN})
	target_compile_options(${name} PRIVATE
		-mmcu=${MCU} -Os -Wall -ffunction-sections -fdata-sections)
	target_link_options(${name} PRIVATE -mmcu=${MCU} -Wl,--gc-sections)
	target_link_libraries(${name} PRIVATE m)

	add_custom_command(TARGET ${name} POST_BUILD
		COMMAND ${AVR_OBJCOPY} -O ihex -R .eeprom ${name}.elf ${name}.hex
		COMMAND ${AVR_OBJDUMP} -d -S ${name}.elf > ${name}.lst
		COMMAND ${AVR_SIZE} --mcu=${MCU} -C ${name}.elf
		BYPRODUCTS ${name}.hex ${name}.lst)

	add_custom_target(upload_${name}
		COMMAND avrdude -p ${MCU} -c arduino -P ${AVR_PORT} -b ${AVR_BAUD}
		        -U flash:w:${name}.hex:i
		DEPENDS ${name})
endfunction()

avr_firmware(midi2aux)
avr_firmware(midi2aux_poly
	POLY_VOICES=${POLY_VOICES} POLY_FS=${POLY_FS}
	POLY_PWM_TOP=${POLY_PWM_TOP} POLY_ACC_BITS=${POLY_ACC_BITS})
