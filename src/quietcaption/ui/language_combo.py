from PySide6.QtWidgets import QComboBox


class CapabilityLanguageCombo(QComboBox):
    def __init__(self, registry, model, leading_label: str, leading_code: str, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.completer().setFilterMode(self.completer().filterMode())
        self.addItem(leading_label, leading_code)
        for language in registry.for_model(model):
            self.addItem(f"{language.display_name}  [{language.code}]", language.code)
        self.setAccessibleName(leading_label)

    def code(self) -> str:
        return self.currentData() or ""

