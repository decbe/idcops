// const gettext = window.gettext || function (text) { return text; };

// 配置对象
const SELECTORS = {
  mainForm: '#main-form',
  nodeList: '.node-list',
  nodeForm: '.node-form',
  addButton: '#add-node-btn',
  totalForms: '#id_nodes-TOTAL_FORMS',
  formTemplate: '#empty-form-template'
};

class PatchCordForm {
  constructor() {
    this.nodeList = document.querySelector(SELECTORS.nodeList);
    // 用于存储所有 Choices 实例
    this.choicesInstances = new Map();
    this.init();
  }

  init() {
    if (!this.nodeList) {
      console.error('找不到节点列表容器');
      return;
    }
    // 初始化已存在的节点
    document.querySelectorAll(SELECTORS.nodeForm).forEach((node, index) => {
      this.initNodeSelects(node, index);
      this.bindNodeEvents(node, index);
    });

    // 绑定添加节点按钮事件
    const addButton = document.querySelector(SELECTORS.addButton);
    if (addButton) {
      addButton.addEventListener('click', () => this.addNewNode());
    }

    const mainSelects = document.querySelectorAll(`${SELECTORS.mainForm} select.select`);
    mainSelects.forEach((select) => {
      // 初始化main form select
      new Choices(select, {
        removeItemButton: true,
        searchEnabled: true,
        searchPlaceholderValue: `搜索${select.getAttribute('placeholder')?.replace('选择', '')}`,
        shouldSort: false,
        noResultsText: '没有找到匹配项',
        itemSelectText: '点击选择',
        loadingText: '加载中...',
        noChoicesText: '没有可选择的选项',
        addItemText: (value) => `按回车键添加 "${value}"`,
        maxItemText: (maxItemCount) => `最多只能选择${maxItemCount}项`,
        customAddItemText: '只能添加符合此规则的选项',
        duplicateItemsAllowed: false,
      });
    });

    // 触发节点颜色change事件
    const firstNodeColor = document.querySelector(`${SELECTORS.nodeForm} select[name="nodes-0-color"]`);
    firstNodeColor.dispatchEvent(new Event('change'));
    // 触发端口类型change事件
    this.bindLableModeChangeEvent();

  }

  // 初始化节点的选择器
  initNodeSelects(node, index) {
    console.log('初始化节点选择器:', index);
    const selects = node.querySelectorAll('select.select');
    selects.forEach(select => {
      // 获取选择器类型（rack, device, port_name, tenant）
      const selectType = select.name.split(`nodes-${index}-`)[1];
      const instanceKey = `${selectType}-${index}`;

      // 如果已经初始化过，先销毁
      if (this.choicesInstances.has(instanceKey)) {
        this.choicesInstances.get(instanceKey).destroy();
        this.choicesInstances.delete(instanceKey);
      }

      // 如果元素上已经有 Choices 实例，也要销毁
      if (select.choices) {
        select.choices.destroy();
      }

      let choiceConfig = {
        removeItemButton: true,
        searchEnabled: true,
        searchPlaceholderValue: `搜索${select.getAttribute('data-placeholder')?.replace('选择', '')}...`,
        shouldSort: false,
        noResultsText: '没有找到匹配项',
        itemSelectText: '点击选择',
        loadingText: '加载中...',
        noChoicesText: '没有可选择的选项',
        addItemText: (value) => `按回车键添加 "${value}"`,
        maxItemText: (maxItemCount) => `最多只能选择${maxItemCount}项`,
        customAddItemText: '只能添加符合此规则的选项',
        duplicateItemsAllowed: false,
      }
      if ((select.name.endsWith('color')) || (select.name === 'color')) {
        this.addColors(select, choiceConfig);
      }
      // 重新初始化并保存实例
      const choices = new Choices(select, choiceConfig);

      this.choicesInstances.set(instanceKey, choices);
      // console.log(`已初始化并保存 Choices 实例: ${instanceKey}`);
    });
  }

  // 获取 Choices 实例
  getChoicesInstance(type, index) {
    const instanceKey = `${type}-${index}`;
    const instance = this.choicesInstances.get(instanceKey);
    if (!instance) {
      // console.warn(`未找到 Choices 实例: ${instanceKey}`);
    }
    return instance;
  }

  // 清理 Choices 实例
  clearChoicesInstances(index) {
    ['rack', 'device', 'port_name', 'tenant', 'port_type'].forEach(type => {
      const instanceKey = `${type}-${index}`;
      if (this.choicesInstances.has(instanceKey)) {
        try {
          this.choicesInstances.get(instanceKey).destroy();
          this.choicesInstances.delete(instanceKey);
          // console.log(`已清理 Choices 实例: ${instanceKey}`);
        } catch (error) {
          console.error(`清理 Choices 实例失败: ${instanceKey}`, error);
        }
      }
    });
  }

  // 添加新节点
  addNewNode() {
    const totalForms = document.querySelectorAll(SELECTORS.nodeForm).length;
    const templateNode = document.querySelector('div.panel.panel-default.node-form[data-form-index="0"]');

    if (!templateNode) {
      console.error('找不到表单模板');
      return;
    }

    // 克隆模板前清理旧的实例
    this.clearChoicesInstances(totalForms);

    // 克隆模板
    const newNode = templateNode.cloneNode(true);

    // 清理克隆节点上的 Choices 相关属性
    newNode.querySelectorAll('select.select').forEach(select => {
      select.classList.remove('choices__input');
      select.removeAttribute('data-choice');
      // 移除所有 Choices 相关的包装元素
      const wrapper = select.closest('.choices');
      if (wrapper) {
        wrapper.parentNode.insertBefore(select, wrapper);
        wrapper.remove();
      }
    });

    // 更新表单索引
    this.updateFormIndex(newNode, totalForms);

    // 添加到列表
    this.nodeList.appendChild(newNode);

    // 初始化选择器和绑定事件
    this.initNodeSelects(newNode, totalForms);

    // 清空新节点的选择器
    newNode.querySelectorAll('select.select').forEach(select => {
      const selectType = select.name.split(`nodes-${totalForms}-`)[1];
      const instanceKey = `${selectType}-${totalForms}`;
      this.choicesInstances.get(instanceKey).setChoiceByValue('');
    });
    newNode.querySelector(`input[name="nodes-${totalForms}-rack_unit"]`).value = '';
    newNode.querySelector(`input[name="nodes-${totalForms}-length"]`).value = 0;

    // 绑定节点事件
    this.bindNodeEvents(newNode, totalForms);

    // 更新表单总数
    document.querySelector(SELECTORS.totalForms).value = totalForms + 1;

    // 触发节点颜色change事件
    const prevNode = newNode.previousSibling;
    const prevNodeColor = prevNode.querySelector(`select[name="nodes-${totalForms - 1}-color"]`);
    prevNodeColor.dispatchEvent(new Event('change'));

    // console.log('新节点已添加:', {
    //   totalForms,
    //   nodeForm: newNode,
    //   formIndex: newNode.dataset.formIndex
    // });
  }

  // 绑定节点事件
  bindNodeEvents(node, index) {
    // console.log('绑定节点事件:', index);

    // 节点类型变化
    const nodeTypeInputs = node.querySelectorAll(`input[name="nodes-${index}-node_type"]`);
    nodeTypeInputs.forEach(input => {
      input.addEventListener('change', async (e) => {
        // console.log('节点类型变化:', e.target.value);
        const rackChoices = this.getChoicesInstance('rack', index);
        const fieldEle = rackChoices.passedElement.element;
        let fetchPath = fieldEle.getAttribute('data-url');
        let params = fieldEle.getAttribute('data-params');
        fetchPath = input.value == 'patch_panel' ? `${fetchPath}?rack_type=${input.value}&${params}` : `${fetchPath}?${params}`;
        // fetchPath = `${fetchPath}&${params}`;
        // console.log(fetchPath)
        if (!rackChoices || !rackChoices._store) {
          console.error(`未找到机柜选择器实例或其存储: rack-${index}`);
          return;
        }
        if (rackChoices.getValue() && rackChoices.getValue().value !== '') {
          // console.log('机柜选择器已选择:', rackChoices.getValue().value);
          return;
        }

        try {
          const response = await fetch(fetchPath);
          const data = await response.json();
          // console.log('获取到机柜数据:', data);

          // 更新机柜选项
          rackChoices.clearStore();
          rackChoices.setChoices([
            { value: '', label: '---------' },
            ...data.results.map(item => ({
              value: item.id,
              label: item._repr
            }))
          ]);

          // 清空设备和端口
          this.clearDeviceAndPort(index);
        } catch (error) {
          console.error('加载机柜选项失败:', error);
        }
      });
    });

    // 机柜变化
    const rackSelect = node.querySelector(`select[name="nodes-${index}-rack"]`);
    if (rackSelect) {
      rackSelect.addEventListener('change', async (e) => {
        // console.log('机柜变化:', e.target.value);
        const deviceChoices = this.getChoicesInstance('device', index);
        const fetchPath = deviceChoices.passedElement.element.getAttribute('data-url')
        const nodeType = node.querySelector(`input[name="nodes-${index}-node_type"]:checked`)?.value;

        if (!deviceChoices || !deviceChoices._store) {
          console.error(`未找到设备选择器实例或其存储: device-${index}`);
          return;
        }

        if (!nodeType) {
          console.error('未选择节点类型');
          return;
        }

        if (e.target.value) {
          try {
            const response = await fetch(`${fetchPath}?rack=${e.target.value}`);
            const data = await response.json();
            // console.log('获取到设备数据:', data);

            // 更新设备选项
            deviceChoices.clearStore();
            deviceChoices.setChoices([
              { value: '', label: '---------' },
              ...data.results.map(item => ({
                value: item.id,
                label: item._repr,
                customProperties: {
                  tenantId: item.tenant,
                  position: item.position,
                  rackId: item.rack
                }
              }))
            ]);

            // 清空端口
            this.clearPort(index);
          } catch (error) {
            console.error('加载设备选项失败:', error);
          }
        } else {
          // 如果没有选择机柜，清空设备和端口
          this.clearDeviceAndPort(index);
        }
      });
    }

    // 设备变化
    this.bindDeviceChangeEvent(node, index);
    // 颜色变化
    this.bindColorChangeEvent(node, index);
    // 端口类型变化
    this.bindPortTypeChangeEvent(node, index);
    // 长度变化
    this.bindLengthChangeEvent(node, index);
    // 端口变化
    this.bindPortNameChangeEvent(node, index);
  }

  bindPortNameChangeEvent(node, index) {
    const portSelect = node.querySelector(`select[name="nodes-${index}-port_name"]`);
    if (portSelect && (index >= 1)) {
      portSelect.addEventListener('change', async (e) => {
        await this.generateCableLabelByNodes('port', index);
      });

      // 触发模式change事件
      const labelMode = document.querySelector(`input[name="cable_label_mode"]:checked`);
      labelMode.dispatchEvent(new Event('change'));
    }
  }

  addColors(select, choiceConfig) {
    // 针对 color 字段的特殊处理
    if ((select.name.endsWith('color')) || (select.name === 'color')) {

      choiceConfig.callbackOnCreateTemplates = function (template) {
        return {
          choice: (classNames, data) => {
            if (!data.value) return template(`
								<div style="margin-bottom: 3px; padding: 3px 0;" data-select-text="${this.config.itemSelectText}" data-choice data-choice-selectable data-id="${data.id}" data-value="${data.value}" role="option">
										<span style="margin: 0 10px; height:16px; display: inline-block;">${data.label}</span>
								</div>
							`);

            return template(`
								<div style="margin-bottom: 3px;" data-select-text="${this.config.itemSelectText}" data-choice data-choice-selectable data-id="${data.id}" data-value="${data.value}" role="option">
										<span class="label bg-${data.value}" style="margin: 0 5px; width:90px; height:12px; display: inline-block;"></span>${data.label}
								</div>
							`);
          },
          item: (classNames, data) => {
            if (!data.value) return template(`
								<div data-item data-id="${data.id}" data-value="${data.value}">
										<span style="margin-right: 5px; font-size: 85%;">${data.label}</span>
										<button type="button" class="choices__button" aria-label="Remove item: exclusive" data-button="">Remove item</button>
								</div>
							`);

            return template(`
								<div data-item data-id="${data.id}" data-value="${data.value}">
										<span class="label bg-${data.value}" style="margin-right: 5px; width:100px; font-size: 85%;">${data.label}</span>
										<button type="button" class="choices__button" aria-label="Remove item: exclusive" data-button="">Remove item</button>
								</div>
							`);
          }
        };
      };
    }
  }

  // 颜色变化事件处理
  bindColorChangeEvent(node, index) {
    const colorSelect = node.querySelector(`select[name="nodes-${index}-color"]`);
    if (colorSelect) {
      colorSelect.addEventListener('change', async (e) => {
        // 判断当前节点是第几个，如果是奇数节点，那么颜色跟随上一个
        // 如果是偶数节点，同步颜色到下一个
        if ((index % 2) === 0) {
          // 如果是偶数节点，同步颜色到下一个, 包含0值，并且设置下一个节点为 readonly
          const nextNode = node.nextSibling;
          if (!nextNode) {
            return
          }
          const nextColorSelect = nextNode.querySelector(`select[name="nodes-${index + 1}-color"]`);
          if (nextColorSelect) {
            // 如果又下一个节点，那么需要同步，并且锁定，
            const choiceInstance = this.getChoicesInstance('color', index + 1);
            choiceInstance.setChoiceByValue(e.target.value);
          }
        }
      });
    }
  }

  // 绑定端口类型变化事件处理
  bindPortTypeChangeEvent(node, index) {
    const portTypeSelect = node.querySelector(`select[name="nodes-${index}-port_type"]`);
    if (portTypeSelect) {
      portTypeSelect.addEventListener('change', async (e) => {
        if ((index % 2) === 0) {
          const nextNode = node.nextSibling;
          if (!nextNode) {
            return
          }
          const nextPortTypeSelect = nextNode.querySelector(`select[name="nodes-${index + 1}-port_type"]`);
          if (nextPortTypeSelect) {
            // 如果又下一个节点，那么需要同步，并且锁定，
            const choiceInstance = this.getChoicesInstance('port_type', index + 1);
            choiceInstance.setChoiceByValue(e.target.value);
          }
        }
      })
    }
  }

  // 线缆长度变化事件处理
  bindLengthChangeEvent(node, index) {
    const lengthInput = node.querySelector(`input[name="nodes-${index}-length"]`);
    if (lengthInput) {
      lengthInput.addEventListener('change', async (e) => {
        if ((index % 2) === 0) {
          const value = e.target.value;
          const nextNode = node.nextSibling;
          if (!nextNode) {
            return
          }
          const nextLengthInput = nextNode.querySelector(`input[name="nodes-${index + 1}-length"]`);
          if (nextLengthInput) {
            // 如果又下一个节点，那么需要同步，并且锁定，
            nextLengthInput.value = value;
            nextLengthInput.setAttribute('readonly', true);
          }
        }
      })
    }
  }

  // 线缆标签flag
  async getCableFlag(mask) {
    const flagMap = { "100": "<=CRo=>", "010": "<=CRa=>", "001": "<=LRa=>", "000": "<=CRd=>" };
    return flagMap[mask];
  }

  // 根据选择的线缆标签模式和节点信息自动生成标签，填入线缆标签供用户二次修改
  async generateCableLabelByNodes(by_field, index) {
    if (index >= 1) {
      const fetchPath = document.querySelector(`${SELECTORS.mainForm} span[name="cable-labels-api"]`).getAttribute('data-url');
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
      const firstNode = document.querySelector('.node-form[data-form-index="0"]');
      const lastIndex = document.querySelector(SELECTORS.totalForms).value - 1;
      const lastNode = document.querySelector(`.node-form[data-form-index="${lastIndex}"]`);
      const aDevice = firstNode.querySelector('select[name="nodes-0-device"]');
      const aPort = firstNode.querySelector(`select[name="nodes-0-port_name"]`);
      const zDevice = lastNode.querySelector(`select[name="nodes-${lastIndex}-device"]`);
      const zPort = lastNode.querySelector(`select[name="nodes-${lastIndex}-port_name"]`);
      let apoint, zpoint;
      if (by_field === 'device') {
        apoint = aDevice.value;
        zpoint = zDevice.value;
      }
      if (by_field == 'port') {
        apoint = aPort.value;
        zpoint = zPort.value;
      }
      const response = await fetch(fetchPath, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify({ by_field: by_field, apoint: apoint, zpoint: zpoint })
      });
      const data = await response.json()
      if (data.status == 'success' && data.results) {
        for (const [key, value] of Object.entries(data.results)) {
          const labelArea = document.querySelector(`${SELECTORS.mainForm} #id_cable_label_mode`);
          const input = labelArea.querySelector(`input[value="${key}"]`);
          if (input) {
            input.setAttribute("data-label-value", value);
          }
        }
        // 触发模式change事件
        const labelMode = document.querySelector(`input[name="cable_label_mode"]:checked`);
        labelMode.dispatchEvent(new Event('change'));
      }
    }
  }

  // 主表单端口模式变化
  bindLableModeChangeEvent() {
    const labelInput = document.querySelector(`${SELECTORS.mainForm} #id_cable_label`);
    document.querySelectorAll(`input[name="cable_label_mode"]`).forEach((el) => {
      el.addEventListener('change', async (e) => {
        const labelValue = e.target.getAttribute('data-label-value');
        const objNullVal = ((labelInput.getAttribute('data-object-pk') !== 0) && labelInput.value == '');
        const nullObj = (labelInput.getAttribute('data-object-pk') == '0');
        if (labelValue && (nullObj || objNullVal)) {
          labelInput.value = labelValue;
          labelInput.setAttribute('value-from-fetch', true);
        }
      });
    });
  }

  // 设备变化事件处理
  bindDeviceChangeEvent(node, index) {
    const deviceSelect = node.querySelector(`select[name="nodes-${index}-device"]`);
    if (deviceSelect) {
      deviceSelect.addEventListener('change', async (e) => {
        // console.log('设备变化:', e.target.value);
        const deviceChoices = this.getChoicesInstance('device', index);
        const portChoices = this.getChoicesInstance('port_name', index);
        const choiceEle = portChoices.passedElement.element;
        const fetchPath = choiceEle.getAttribute('data-url');
        const queryParams = choiceEle.getAttribute('data-params');


        if (!portChoices) {
          console.error(`未找到端口选择器实例: port_name-${index}`);
          return;
        }

        if (e.target.value) {
          try {
            // 获取端口数据
            const response = await fetch(`${fetchPath}?device=${e.target.value}&${queryParams}`);
            const data = await response.json();
            // console.log('获取到端口数据:', data);

            // 更新端口选项
            portChoices.clearStore();
            portChoices.setChoices([
              { value: '', label: '---------' },
              ...data.results.map(item => ({
                value: item.id,
                label: item._repr
              }))
            ]);

            // console.log(deviceChoices, deviceChoices._store.activeChoices)
            // console.log(typeof (e.target.value))
            // 更新租户和U位
            if (deviceChoices) {
              // 获取当前选中的选项
              const selectedChoice = deviceChoices._store.activeChoices.find(
                choice => choice.value === parseInt(e.target.value)
              );
              // console.log('选中的设备完整数据:', selectedChoice);

              if (selectedChoice?.customProperties) {
                const { tenantId, position } = selectedChoice.customProperties;
                // console.log('设备附加属性:', { tenantId, position });

                // 更新租户
                const tenantChoices = this.getChoicesInstance('tenant', index);
                if (tenantChoices && tenantId) {
                  // console.log('设置租户:', tenantId);
                  tenantChoices.setChoiceByValue(tenantId.toString());
                }

                // 更新U位
                const rackUnitInput = node.querySelector(`input[name="nodes-${index}-rack_unit"]`);
                if (rackUnitInput && position) {
                  // console.log('设置U位:', position);
                  rackUnitInput.value = position;
                }
                // 同步标签
                await this.generateCableLabelByNodes('device', index);

              } else {
                console.warn('设备数据中没有找到附加属性');
              }
            }
          } catch (error) {
            console.error('加载端口选项或更新租户U位失败:', error);
            // console.log('设备选择器状态:', deviceChoices);
          }
        } else {
          // 如果没有选择设备，清空端口选项
          portChoices.clearStore();
          portChoices.setChoices([{ value: '', label: '---------' }]);

          // 清空租户和U位
          const tenantChoices = this.getChoicesInstance('tenant', index);
          const rackUnitInput = node.querySelector(`input[name="nodes-${index}-rack_unit"]`);

          if (tenantChoices) {
            tenantChoices.setChoiceByValue('');
          }
          if (rackUnitInput) {
            rackUnitInput.value = '';
          }
        }
      });
    }
  }

  // 清空设备和端口选择器
  clearDeviceAndPort(index) {
    try {
      const deviceChoices = this.getChoicesInstance('device', index);
      const portChoices = this.getChoicesInstance('port_name', index);

      if (deviceChoices && deviceChoices._store) {
        deviceChoices.clearStore();
        deviceChoices.setChoices([{ value: '', label: '---------' }]);
      }

      if (portChoices && portChoices._store) {
        portChoices.clearStore();
        portChoices.setChoices([{ value: '', label: '---------' }]);
      }

      // 清空租户和U位
      const tenantChoices = this.getChoicesInstance('tenant', index);
      const rackUnitInput = document.querySelector(`input[name="nodes-${index}-rack_unit"]`);

      if (tenantChoices && tenantChoices._store) {
        tenantChoices.setChoiceByValue('');
      }
      if (rackUnitInput) {
        rackUnitInput.value = '';
      }
    } catch (error) {
      console.error('清空设备和端口选择器失败:', error);
    }
  }

  // 清空端口选择器
  clearPort(index) {
    try {
      const portChoices = this.getChoicesInstance('port_name', index);
      if (portChoices && portChoices._store) {
        portChoices.clearStore();
        portChoices.setChoices([{ value: '', label: '---------' }]);
      }
    } catch (error) {
      console.error('清空端口选择器失败:', error);
    }
  }

  // 更新表单索引
  updateFormIndex(form, index) {
    if (!form) {
      console.error('表单元素不存在');
      return;
    }

    // 设置表单索引
    form.dataset.formIndex = index;

    // 更新所有表单元素
    const updateElements = (elements, pattern) => {
      elements.forEach(element => {
        // 更新 name 属性
        if (element.hasAttribute('name')) {
          element.setAttribute('name', element.getAttribute('name').replace(pattern, `nodes-${index}`));
        }

        // 更新 id 属性
        if (element.hasAttribute('id')) {
          element.setAttribute('id', element.getAttribute('id').replace(pattern, `nodes-${index}`));
        }

        // 更新 for 属性（用于 label 元素）
        if (element.hasAttribute('for')) {
          element.setAttribute('for', element.getAttribute('for').replace(pattern, `nodes-${index}`));
        }

        // 更新 label 内容中的索引
        if (element.tagName === 'LABEL') {
          const labelText = element.innerHTML;
          if (labelText.includes('节点 #')) {
            element.innerHTML = labelText.replace(/节点 #\d+/, `节点 #${index + 1}`);
          }
        }
      });
    };

    // 更新所有相关元素
    updateElements(form.querySelectorAll('input, select, label, div[id*="nodes-"]'), /nodes-\d+/);
    updateElements(form.querySelectorAll('[name*="form-"], [id*="form-"]'), /form-\d+/);

    // 更新面板标题
    const titleElement = form.querySelector('.panel-title');
    if (titleElement) {
      titleElement.textContent = `节点 #${index + 1}`;
    }

    // 更新序号隐藏字段
    const sequenceInput = form.querySelector('input[name*="-sequence"]');
    if (sequenceInput) {
      sequenceInput.value = index;
    }

    // 更新所有 label 的文本内容
    form.querySelectorAll('label').forEach(label => {
      const labelHtml = label.innerHTML;
      // 保留原有的 HTML 结构（如 span.text-red）
      if (labelHtml.includes('nodes-')) {
        label.innerHTML = labelHtml.replace(/nodes-\d+/, `nodes-${index}`);
      }
    });

    // 更新所有包含索引的文本节点
    const walker = document.createTreeWalker(
      form,
      NodeFilter.SHOW_TEXT,
      null,
      false
    );

    let node;
    while (node = walker.nextNode()) {
      const text = node.nodeValue;
      if (text.includes('nodes-')) {
        node.nodeValue = text.replace(/nodes-\d+/, `nodes-${index}`);
      }
    }

    // console.log('表单索引已更新:', {
    //   index,
    //   formElement: form,
    //   updatedElements: {
    //     inputs: form.querySelectorAll('input').length,
    //     selects: form.querySelectorAll('select').length,
    //     labels: form.querySelectorAll('label').length,
    //     divs: form.querySelectorAll('div[id*="nodes-"]').length
    //   }
    // });
  }
}

// 初始化表单
document.addEventListener('DOMContentLoaded', () => {
  window.patchCordForm = new PatchCordForm();
});