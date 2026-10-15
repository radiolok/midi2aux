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
set(POLY_VOICES   4     CACHE STRING "Number of voices, 1..16 (build checks CPU budget)")
set(POLY_FS       31250 CACHE STRING "Sample rate, Hz")
set(POLY_PWM_TOP  255   CACHE STRING "Timer2 TOP (255 = 62.5 kHz, 99 = 160 kHz)")
set(POLY_ACC_BITS 24    CACHE STRING "Phase accumulator width (16 or 24)")
option(POLY_SINE_ENV "Poly: pot drives the sine envelope (pluck -> organ -> pad)" ON)
set(POLY_DRIVE    100   CACHE STRING "Poly + envelope: chord gain normalisation, % (100 = never clips, 150..200 = louder chords, may clip)")
set(POT2_ADC      ""    CACHE STRING "Envelope builds: ADC channel of a second pot (attack), e.g. 6 for A6; empty = one pot")

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

set(POLY_DEFS POLY_VOICES=${POLY_VOICES} POLY_FS=${POLY_FS}
	POLY_PWM_TOP=${POLY_PWM_TOP} POLY_ACC_BITS=${POLY_ACC_BITS})
set(ENV_DEFS SINE_ENV)
if(NOT POT2_ADC STREQUAL "")
	list(APPEND ENV_DEFS POT2_ADC=${POT2_ADC})
endif()
if(POLY_SINE_ENV)
	list(APPEND POLY_DEFS ${ENV_DEFS} POLY_DRIVE=${POLY_DRIVE})
endif()

avr_firmware(midi2aux)			# original mono, identical to master
avr_firmware(midi2aux_env ${ENV_DEFS})	# mono + sine envelope on the pot
avr_firmware(midi2aux_poly ${POLY_DEFS})
