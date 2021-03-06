#include <windows.h>
#include <Lmcons.h> // for UNLEN
#include <Winnt.h> // for security attributes constants
#include <aclapi.h> // for ACL
#include <string>
#include <iostream>

using namespace std;

static SECURITY_DESCRIPTOR g_securittyDescriptor = {0};
static SECURITY_ATTRIBUTES g_securityAttributes = { 0 };
static PACL g_acl = NULL;

extern "C" {

static void init() {
	// http://msdn.microsoft.com/en-us/library/windows/desktop/hh448449(v=vs.85).aspx
	// define new Win 8 app related constants
	EXPLICIT_ACCESS explicit_accesses[2];
	memset(&explicit_accesses, 0, sizeof(explicit_accesses));
	// Create a well-known SID for the Everyone group.
	// FIXME: we should limit the access to current user only
	// See this article for details: https://msdn.microsoft.com/en-us/library/windows/desktop/hh448493(v=vs.85).aspx

	PSID everyoneSID = NULL;
	SID_IDENTIFIER_AUTHORITY worldSidAuthority = SECURITY_WORLD_SID_AUTHORITY;
	AllocateAndInitializeSid(&worldSidAuthority, 1,
		SECURITY_WORLD_RID, 0, 0, 0, 0, 0, 0, 0, &everyoneSID);

	// https://services.land.vic.gov.au/ArcGIS10.1/edESRIArcGIS10_01_01_3143/Python/pywin32/PLATLIB/win32/Demos/security/explicit_entries.py

	EXPLICIT_ACCESS& ea = explicit_accesses[0];
	ea.grfAccessPermissions = GENERIC_ALL;
	ea.grfAccessMode = SET_ACCESS;
	ea.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT;
	ea.Trustee.pMultipleTrustee = NULL;
	ea.Trustee.MultipleTrusteeOperation = NO_MULTIPLE_TRUSTEE;
	ea.Trustee.TrusteeForm = TRUSTEE_IS_SID;
	ea.Trustee.TrusteeType = TRUSTEE_IS_WELL_KNOWN_GROUP;
	ea.Trustee.ptstrName = (LPTSTR)everyoneSID;

	// create SID for app containers
	PSID allAppsSID = NULL;
	SID_IDENTIFIER_AUTHORITY appPackageAuthority = SECURITY_APP_PACKAGE_AUTHORITY;
	AllocateAndInitializeSid(&appPackageAuthority,
		SECURITY_BUILTIN_APP_PACKAGE_RID_COUNT,
		SECURITY_APP_PACKAGE_BASE_RID,
		SECURITY_BUILTIN_PACKAGE_ANY_PACKAGE,
		0, 0, 0, 0, 0, 0, &allAppsSID);

	ea = explicit_accesses[1];
	ea.grfAccessPermissions = GENERIC_ALL;
	ea.grfAccessMode = SET_ACCESS;
	ea.grfInheritance = SUB_CONTAINERS_AND_OBJECTS_INHERIT;
	ea.Trustee.pMultipleTrustee = NULL;
	ea.Trustee.MultipleTrusteeOperation = NO_MULTIPLE_TRUSTEE;
	ea.Trustee.TrusteeForm = TRUSTEE_IS_SID;
	ea.Trustee.TrusteeType = TRUSTEE_IS_GROUP;
	ea.Trustee.ptstrName = (LPTSTR)allAppsSID;

	// create DACL
	SetEntriesInAcl(2, explicit_accesses, NULL, &g_acl);

	// security descriptor
	InitializeSecurityDescriptor(&g_securittyDescriptor, SECURITY_DESCRIPTOR_REVISION);

	// Add the ACL to the security descriptor. 
	SetSecurityDescriptorDacl(&g_securittyDescriptor, TRUE, g_acl, FALSE);

	g_securityAttributes.nLength = sizeof(SECURITY_ATTRIBUTES);
	g_securityAttributes.lpSecurityDescriptor = &g_securittyDescriptor;
	g_securityAttributes.bInheritHandle = FALSE;

	// cleanup
	FreeSid(everyoneSID);
	FreeSid(allAppsSID);
}

static void cleanup() {
	if (g_acl != nullptr)
		LocalFree(g_acl);
}

// References:
// https://msdn.microsoft.com/en-us/library/windows/desktop/aa365588(v=vs.85).aspx
HANDLE connect_pipe(const char* app_name) {
	HANDLE pipe = INVALID_HANDLE_VALUE;
	char username[UNLEN + 1];
	DWORD unlen = UNLEN + 1;
	if (GetUserNameA(username, &unlen)) {
		// add username to the pipe path so it will not clash with other users' pipes.
		char pipe_name[MAX_PATH];
		sprintf(pipe_name, "\\\\.\\pipe\\%s\\%s_pipe", username, app_name);
		const size_t buffer_size = 1024;
		// create the pipe
		pipe = CreateNamedPipeA(pipe_name,
			PIPE_ACCESS_DUPLEX,
			PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_WAIT,
			PIPE_UNLIMITED_INSTANCES,
			buffer_size,
			buffer_size,
			NMPWAIT_USE_DEFAULT_WAIT,
			&g_securityAttributes);

		if (pipe != INVALID_HANDLE_VALUE) {
			// try to connect to the named pipe
			// NOTE: this is a blocking call
			if (FALSE == ConnectNamedPipe(pipe, NULL)) {
				// fail to connect the pipe
				CloseHandle(pipe);
				pipe = INVALID_HANDLE_VALUE;
			}
		}
	}
	return pipe;
}

void close_pipe(HANDLE pipe) {
	FlushFileBuffers(pipe);
	DisconnectNamedPipe(pipe);
	CloseHandle(pipe);
}

int read_pipe(HANDLE pipe, char* buf, unsigned long len, unsigned long* error) {
	DWORD read_len = 0;
	BOOL success = ReadFile(pipe, buf, len, &read_len, NULL);
	if (error != nullptr)
		*error = success ? 0 : (unsigned long)GetLastError();
	return (int)read_len;
}

int write_pipe(HANDLE pipe, const char* data, unsigned long len, unsigned long* error) {
	DWORD write_len = 0;
	BOOL success = WriteFile(pipe, data, len, &write_len, NULL);
	if (error != nullptr)
		*error = success ? 0 : (unsigned long)GetLastError();
	return (int)write_len;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD  ul_reason_for_call, LPVOID lpReserved) {
	switch (ul_reason_for_call) {
	case DLL_PROCESS_ATTACH:
		::DisableThreadLibraryCalls(hModule); // disable DllMain calls due to new thread creation
		init();
		break;
	case DLL_PROCESS_DETACH:
		cleanup();
		break;
	}
	return TRUE;
}


} // extern "C"
