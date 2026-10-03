// Native Windows compiler driver. These options change C++ generation only;
// the pinned Verilator executable and course RTL/simulation driver are unchanged.
#include <windows.h>
#include <cstdio>
#include <cstring>
#include <iterator>
#include <string>
#include <vector>

static std::string quote(const char *argument) {
    std::string output = "\"";
    unsigned backslashes = 0;
    for (const char *p = argument; *p; ++p) {
        if (*p == '\\') { ++backslashes; continue; }
        output.append(*p == '"' ? 2 * backslashes + 1 : backslashes, '\\');
        output += *p;
        backslashes = 0;
    }
    output.append(2 * backslashes, '\\');
    return output + '"';
}

int main(int argc, char **argv) {
    const char *binary = "F:/CPU2026CourseTools/win54fc150/verilator/bin/verilator_bin.exe";
    std::vector<const char *> arguments{binary};
    bool compiling = false;
    for (int i = 1; i < argc; ++i)
        compiling = compiling || std::strcmp(argv[i], "--cc") == 0;
    if (compiling) {
        const char *extra[] = {"--unroll-count", "1024", "--unroll-stmts", "1000000",
                              "--output-split", "2000", "--output-split-cfuncs", "2000"};
        arguments.insert(arguments.end(), std::begin(extra), std::end(extra));
    }
    for (int i = 1; i < argc; ++i) arguments.push_back(argv[i]);
    std::string command;
    for (const auto argument : arguments) command += quote(argument) + ' ';
    STARTUPINFOA startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput = GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError = GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process{};
    if (!CreateProcessA(binary, command.data(), nullptr, nullptr, TRUE,
                        CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process)) {
        std::fprintf(stderr, "Cannot start pinned Verilator: Windows error %lu\n", GetLastError());
        return 127;
    }
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD status = 127;
    GetExitCodeProcess(process.hProcess, &status);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return static_cast<int>(status);
}
