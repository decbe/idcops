/**
 * 设备表单动态交互的JavaScript函数
 */
const choicesMap = new Map();
// 初始化表单
document.addEventListener('DOMContentLoaded', function() {
    // 绑定设备型号变化事件
    const modelSelect = document.querySelector('select[name="model"]');
    if (modelSelect) {
        modelSelect.addEventListener('change', function() {
            updateDeviceFormFromModel(this);
        });
    }

    // 初始化Choices.js增强下拉框
    initChoicesSelect();
});

/**
 * 当设备型号变化时，自动更新表单中的设备类型和高度
 * @param {HTMLSelectElement} modelSelect - 设备型号选择框元素
 */
function updateDeviceFormFromModel(modelSelect) {
    // 获取选中的选项
    const selectedOption = modelSelect.options[modelSelect.selectedIndex];
    if (!selectedOption || !selectedOption.value) {
        return;
    }

    // 获取设备型号数据（从API获取）
    fetch(`/api/v1/dcrm/devicemodel/?id=${selectedOption.value}`)
        .then(response => response.json())
        .then(modelData => {
            // 更新设备类型字段
            modelData = modelData?.results[0];
            if (modelData.type) {
                const typeField = document.querySelector('select[name="type"]');
                if (typeField) {
                    typeField.value = modelData.type;
                    // 如果使用了Select2或Choices.js，需要触发更新
                    triggerSelectUpdate(typeField);
                }
            }

            // 更新设备高度字段
            if (modelData.height) {
                const heightField = document.querySelector('input[name="height"]');
                if (heightField) {
                    heightField.value = modelData.height;
                }
            }
        })
        .catch(error => {
            console.error('获取设备型号数据失败:', error);
        });
}

/**
 * 初始化使用Choices.js的下拉选择框
 */
function initChoicesSelect() {
    // 查找所有带有object-select属性的选择框
    const choicesElements = document.querySelectorAll('select.object-select');
    
    if (typeof Choices !== 'undefined') {

        choicesElements.forEach(element => {
            // 如果元素已经初始化了Choices，跳过
            if (element.classList.contains('choices__input')) {
                return;
            }
            
            // 从元素的data属性中获取配置
            const config = {
                removeItemButton: element.dataset.choicesRemoveItemButton === 'true',
                searchEnabled: element.dataset.choicesSearchEnabled === 'true',
                searchPlaceholderValue: element.dataset.choicesSearchPlaceholder || '输入关键字搜索...',
                placeholderValue: element.dataset.choicesPlaceholder || '请选择...',
                loadingText: element.dataset.choicesLoadingText || '加载中...',
                noResultsText: element.dataset.choicesNoResultsText || '未找到匹配项',
                noChoicesText: element.dataset.choicesNoChoicesText || '无可选项',
                itemSelectText: element.dataset.choicesItemSelectText || '点击选择',
            };
            
            // 初始化Choices.js
            // choices = new Choices(element, config);
            choicesMap.set(element, new Choices(element, config));
        });
    }
}

/**
 * 触发选择框更新（针对增强型选择框如Select2或Choices.js）
 * @param {HTMLSelectElement} selectElement - 选择框元素
 */
function triggerSelectUpdate(selectElement) {
    // 对于原生选择框，触发change事件
    const event = new Event('change', { bubbles: true });
    selectElement.dispatchEvent(event);
    
    // 对于Choices.js
    const choice = choicesMap.get(selectElement);
    if (typeof Choices !== 'undefined' && choice) {
        choice.setChoiceByValue(selectElement.value);
    }
    
    // 对于Select2
    if (window.jQuery && window.jQuery.fn.select2 && window.jQuery(selectElement).data('select2')) {
        window.jQuery(selectElement).trigger('change');
    }
} 