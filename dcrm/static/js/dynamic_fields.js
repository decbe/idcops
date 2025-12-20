/**
 * dynamic_fields.js - 处理动态依赖字段
 * 
 * 此脚本处理基于Choices.js的依赖字段更新，无需表单提交
 * 依赖于choices.js
 */

document.addEventListener('DOMContentLoaded', function() {
    // 初始化所有动态选择字段
    initializeDynamicSelects();
});

/**
 * 初始化所有具有依赖关系的选择字段
 */
function initializeDynamicSelects() {
    // 查找所有带有data-dynamic-filter属性的选择字段
    const dynamicSelects = document.querySelectorAll('select[data-dynamic-filter]');
    
    // 为每个字段设置监听器
    dynamicSelects.forEach(select => {
        const dependencies = select.getAttribute('data-dependencies');
        if (!dependencies) return;
        
        // 解析依赖字段名称
        const dependencyFields = dependencies.split(',').map(d => d.trim());
        const fieldName = select.getAttribute('data-field-name') || select.getAttribute('name');
        const apiUrl = select.getAttribute('data-api-url');
        
        if (!apiUrl) {
            console.error('缺少API URL:', fieldName);
            return;
        }
        
        // 为每个依赖字段添加变更监听器
        dependencyFields.forEach(depField => {
            // 查找依赖字段（考虑表单前缀）
            const depElement = findDependencyElement(depField);
            if (!depElement) {
                console.warn(`未找到依赖字段 ${depField} 对于 ${fieldName}`);
                return;
            }
            
            // 添加变更事件处理
            depElement.addEventListener('change', function() {
                updateDependentField(select, dependencyFields);
            });
            
            // 如果是Choices.js实例，监听其选择事件
            if (depElement.classList.contains('choices-select')) {
                monitorChoicesChange(depElement, function() {
                    updateDependentField(select, dependencyFields);
                });
            }
        });
        
        // 初始加载
        updateDependentField(select, dependencyFields);
    });
}

/**
 * 查找依赖字段元素，处理表单前缀
 */
function findDependencyElement(fieldName) {
    // 尝试直接匹配字段名
    let element = document.querySelector(`[name="${fieldName}"]`);
    if (element) return element;
    
    // 尝试匹配带前缀的字段名（表单前缀处理）
    const prefixedElements = document.querySelectorAll(`[name$="-${fieldName}"]`);
    if (prefixedElements.length > 0) {
        return prefixedElements[0]; // 返回第一个匹配
    }
    
    return null;
}

/**
 * 监听Choices.js选择变化
 */
function monitorChoicesChange(element, callback) {
    // 检查元素是否已初始化为Choices实例
    if (element.choices) {
        element.choices.passedElement.element.addEventListener('choice', function() {
            setTimeout(callback, 50); // 短暂延迟确保值已更新
        });
    } else {
        // 如果尚未初始化，增加事件委托
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'data-choice') {
                    setTimeout(callback, 50);
                }
            });
        });
        
        observer.observe(element, { attributes: true });
    }
}

/**
 * 更新依赖字段的选项
 */
function updateDependentField(selectElement, dependencyFields) {
    // 获取API URL
    const apiUrl = selectElement.getAttribute('data-api-url');
    if (!apiUrl) return;
    
    // 构建查询参数
    const params = new URLSearchParams();
    let hasValues = false;
    
    // 收集所有依赖字段的值
    dependencyFields.forEach(depField => {
        const depElement = findDependencyElement(depField);
        if (!depElement) return;
        
        let value = getElementValue(depElement);
        if (value !== null && value !== '') {
            params.append(depField, value);
            hasValues = true;
        }
    });
    
    // 如果没有依赖值，则清空选项
    if (!hasValues) {
        clearOptions(selectElement);
        return;
    }
    
    // 添加额外参数
    params.append('_select2', 'true'); // 通知后端这是一个AJAX请求
    
    // 发送AJAX请求获取更新的选项
    fetch(`${apiUrl}?${params.toString()}`)
        .then(response => response.json())
        .then(data => {
            updateSelectOptions(selectElement, data);
        })
        .catch(error => {
            console.error('更新依赖字段失败:', error);
        });
}

/**
 * 获取元素的值，支持不同类型的表单元素
 */
function getElementValue(element) {
    // 处理选择元素
    if (element.tagName === 'SELECT') {
        return element.value;
    }
    
    // 处理Choices.js实例
    if (element.classList.contains('choices-select')) {
        const choicesInstance = element.choices;
        if (choicesInstance) {
            const selectedValue = choicesInstance.getValue(true);
            return selectedValue;
        }
    }
    
    // 处理复选框
    if (element.type === 'checkbox') {
        return element.checked ? element.value : '';
    }
    
    // 处理单选按钮
    if (element.type === 'radio') {
        const name = element.name;
        const checkedRadio = document.querySelector(`input[name="${name}"]:checked`);
        return checkedRadio ? checkedRadio.value : '';
    }
    
    // 默认处理其他输入元素
    return element.value;
}

/**
 * 清空选择字段的选项
 */
function clearOptions(selectElement) {
    // 保留第一个空选项（如果存在）
    while (selectElement.options.length > 1) {
        selectElement.remove(selectElement.options.length - 1);
    }
    
    // 如果没有空选项则添加一个
    if (selectElement.options.length === 0) {
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = '---------';
        selectElement.appendChild(emptyOption);
    }
    
    // 如果是Choices.js实例，刷新
    if (selectElement.choices) {
        selectElement.choices.setChoiceByValue('');
        selectElement.choices.refresh();
    }
    
    // 触发change事件，通知依赖此字段的其他字段
    const event = new Event('change', { bubbles: true });
    selectElement.dispatchEvent(event);
}

/**
 * 更新选择字段的选项
 */
function updateSelectOptions(selectElement, data) {
    // 保存当前值
    const currentValue = selectElement.value;
    
    // 清空选项，可能保留"空选项"
    clearOptions(selectElement);
    
    // 添加新选项
    if (Array.isArray(data)) {
        data.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id || item.value || '';
            option.textContent = item.text || item.name || item.label || '';
            selectElement.appendChild(option);
        });
    } else if (typeof data === 'object' && data.results) {
        // 处理DRF风格的分页响应
        data.results.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id || item.value || '';
            option.textContent = item.text || item.name || item.label || item._repr || '';
            selectElement.appendChild(option);
        });
    }
    
    // 尝试恢复之前的值（如果还存在）
    if (currentValue) {
        selectElement.value = currentValue;
    }
    
    // 如果是Choices.js实例，刷新
    if (window.Choices && selectElement.classList.contains('choices-select')) {
        // 如果尚未初始化，则初始化
        if (!selectElement.choices) {
            new Choices(selectElement, {
                searchEnabled: true,
                itemSelectText: '',
                shouldSort: false,
                placeholder: true,
                placeholderValue: '---------'
            });
        } else {
            // 刷新现有实例
            selectElement.choices.refresh();
        }
    }
    
    // 触发change事件，通知依赖此字段的其他字段
    const event = new Event('change', { bubbles: true });
    selectElement.dispatchEvent(event);
} 