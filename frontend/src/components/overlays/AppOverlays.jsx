import TestCaseEditorModal from "./modals/TestCaseEditorModal.jsx";
import CaseConfirmationModal from "./modals/CaseConfirmationModal.jsx";
import ConfirmationModal from "./modals/ConfirmationModal.jsx";
import PasswordModal from "./modals/PasswordModal.jsx";
import ValidatorModal from "./modals/ValidatorModal.jsx";
import ProjectAccessModal from "./modals/ProjectAccessModal.jsx";
import JobLogModal from "./modals/JobLogModal.jsx";
import ToastHost from "./modals/ToastHost.jsx";
import HtmlModal from "./modals/HtmlModal.jsx";
import ImportSheetModal from "../../features/imports/components/ImportSheetModal.jsx";
import ImportLibraryModal from "../../features/imports/components/ImportLibraryModal.jsx";

export default function AppOverlays() {
  return (
    <>
      <TestCaseEditorModal />
      <CaseConfirmationModal />
      <ConfirmationModal />
      <PasswordModal />
      <ValidatorModal />
      <ProjectAccessModal />
      <JobLogModal />
      <ToastHost />
      <HtmlModal />
      <ImportSheetModal />
      <ImportLibraryModal />
    </>
  );
}
