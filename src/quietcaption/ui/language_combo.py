from PySide6.QtWidgets import QComboBox


class CapabilityLanguageCombo(QComboBox):
    def __init__(self, registry, model, leading_label: str, leading_code: str, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.completer().setFilterMode(self.completer().filterMode())
        self.registry = registry
        self.leading_label = leading_label
        self.leading_code = leading_code
        self.set_model(model)
        self.setAccessibleName(leading_label)

    def set_model(self, model) -> None:
        selected = self.code() if self.count() else self.leading_code
        self.clear()
        self.addItem(self.leading_label, self.leading_code)
        if model is not None:
            for language in self.registry.for_model(model):
                self.addItem(f"{language.display_name}  [{language.code}]", language.code)
        index = self.findData(selected)
        self.setCurrentIndex(index if index >= 0 else 0)

    def code(self) -> str:
        return self.currentData() or ""
