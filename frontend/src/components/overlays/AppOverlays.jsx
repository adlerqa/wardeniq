import TestCaseEditorModal from "./modals/TestCaseEditorModal.jsx";
import CaseConfirmationModal from "./modals/CaseConfirmationModal.jsx";
import ConfirmationModal from "./modals/ConfirmationModal.jsx";
import PasswordModal from "./modals/PasswordModal.jsx";
import ValidatorModal from "./modals/ValidatorModal.jsx";
import ExportModal from "./modals/ExportModal.jsx";
import ProjectAccessModal from "./modals/ProjectAccessModal.jsx";
import JobLogModal from "./modals/JobLogModal.jsx";
import ToastHost from "./modals/ToastHost.jsx";
import ImportSheetModal from "./modals/ImportSheetModal.jsx";
import ImportLibraryModal from "./modals/ImportLibraryModal.jsx";

export default function AppOverlays() {
  return (
    <>
      <TestCaseEditorModal />
      <CaseConfirmationModal />
      <ConfirmationModal />
      <PasswordModal />
      <ValidatorModal />
      <ExportModal />
      <ProjectAccessModal />
      <JobLogModal />
      <ToastHost />
      <ImportSheetModal />
      <ImportLibraryModal />
    </>
  );
}
