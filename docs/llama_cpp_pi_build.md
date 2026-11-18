# llama.cpp 在 Pi 4B（CMake 3.16）上的无头构建

Ubuntu 20.04 / Pi 4B 自带 CMake 3.16.3；llama.cpp master 的内置 UI 资源脚本要求 CMake ≥3.18。
本项目使用 FastAPI 托管自己的前端，不需要 llama.cpp 内置 UI，因此做无头构建。

## 1. 下载源码

```bash
cd ~/ai-terminal
curl -L -o llama.cpp.tar.gz https://github.com/ggml-org/llama.cpp/archive/refs/heads/master.tar.gz
tar -xzf llama.cpp.tar.gz
mv llama.cpp-master llama.cpp
cd llama.cpp
```

## 2. 关闭 UI 目标

在 `ui/apps/chat/CMakeLists.txt` **文件最顶部**加入：

```cmake
if(NOT LLAMA_BUILD_UI)
  return()
endif()
```

## 3. 去掉 llama-ui 依赖/链接

编辑 `tools/server/CMakeLists.txt`：

```cmake
# 注释掉
# add_dependencies(${TARGET} llama-ui-assets)

# 从 target_link_libraries 中删除 llama-ui
target_link_libraries(${TARGET} PUBLIC server-context cpp-httplib ${CMAKE_THREAD_LIBS_INIT})
```

## 4. 提供空 ui.h

创建 `tools/server/ui.h`：

```cpp
// Minimal stub for headless llama-server build (no embedded UI assets).
#pragma once

#include <array>
#include <string>

// LLAMA_UI_HAS_ASSETS intentionally not defined.
struct llama_ui_asset {
    std::string           name;
    const unsigned char * data;
    std::size_t           size;
    std::string           etag;
    std::string           type;
};

inline const llama_ui_asset * llama_ui_find_asset(const std::string & name) {
    (void) name;
    return nullptr;
}

inline bool llama_ui_use_gzip() {
    return false;
}

inline const std::array<llama_ui_asset, 0> & llama_ui_get_assets() {
    static const std::array<llama_ui_asset, 0> empty{};
    return empty;
}
```

## 5. 配置与构建

```bash
cmake -S . -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF \
  -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_UI=OFF
cmake --build build --target llama-server -j4
```

产物：`build/bin/llama-server`（约 10–20 分钟，Pi 4B 4 核）。

## 6. 运行

```bash
export LD_LIBRARY_PATH=$HOME/ai-terminal/llama.cpp/build/bin:$LD_LIBRARY_PATH

# LLM
./build/bin/llama-server -m ~/ai-terminal/models/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --host 127.0.0.1 --port 8080 -t 4 -c 2048

# VLM
./build/bin/llama-server -m ~/ai-terminal/models/SmolVLM-500M-Instruct-Q8_0.gguf \
  --mmproj ~/ai-terminal/models/mmproj-SmolVLM-500M-Instruct-Q8_0.gguf \
  --host 127.0.0.1 --port 8081 -t 4 -c 2048
```

## 7. 验证

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8081/health
```

实测：Qwen2.5-0.5B 7.26 tok/s；SmolVLM-500M 单图 34.11s。
