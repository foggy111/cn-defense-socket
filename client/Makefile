# 乙 — 客户端构建
CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -pthread -I../common
LDFLAGS  ?= -pthread

TARGET = client
SRC    = client.cpp

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SRC) ../common/protocol.hpp
	$(CXX) $(CXXFLAGS) -o $@ $(SRC) $(LDFLAGS)

clean:
	rm -f $(TARGET)
