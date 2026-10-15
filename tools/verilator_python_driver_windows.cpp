// Windows executable adapter for the official build.py --verilator option.
// Keep the course build and sim.cpp unchanged. Launch the existing bounded
// Python build driver and supply the Windows weak-symbol timestamp fallback.
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static std::string quote(const char* value) {
    std::string result="\"";
    unsigned slashes=0;
    for(const char* p=value;*p;++p) {
        if(*p=='\\') { ++slashes;continue; }
        result.append(*p=='"'?2*slashes+1:slashes,'\\');
        result+=*p;slashes=0;
    }
    result.append(2*slashes,'\\');
    return result+'"';
}
int main(int argc,char** argv) {
    const char* python=std::getenv("CPU2026_BUILD_PYTHON");
    const char* driver=std::getenv("CPU2026_BUILD_DRIVER");
    const char* timestamp=std::getenv("CPU2026_WINDOWS_TIMESTAMP_SOURCE");
    if(!python || !driver || !timestamp) {
        std::fprintf(stderr,"Missing explicit Windows build adapter environment\n");return 2;
    }
    std::vector<const char*> args{python,driver};
    bool compiling=false;
    for(int i=1;i<argc;++i) {args.push_back(argv[i]);compiling|=std::strcmp(argv[i],"--cc")==0;}
    if(compiling) args.push_back(timestamp);
    std::string command;
    for(const auto arg:args) command+=quote(arg)+' ';
    STARTUPINFOA startup{};startup.cb=sizeof(startup);startup.dwFlags=STARTF_USESTDHANDLES;
    startup.hStdInput=GetStdHandle(STD_INPUT_HANDLE);
    startup.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);
    startup.hStdError=GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process{};
    if(!CreateProcessA(python,command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&process)) {
        std::fprintf(stderr,"Cannot launch build driver: Windows error %lu\n",GetLastError());return 127;
    }
    WaitForSingleObject(process.hProcess,INFINITE);
    DWORD status=127;GetExitCodeProcess(process.hProcess,&status);
    CloseHandle(process.hThread);CloseHandle(process.hProcess);
    return static_cast<int>(status);
}
