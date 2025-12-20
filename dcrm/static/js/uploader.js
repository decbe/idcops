// dcrm/static/js/uploader.js

// 获取 CSRF Token 的通用函数
function getCsrfToken() {
  // 方式1：从 input 获取
  const input = document.querySelector('[name=csrfmiddlewaretoken]');
  if (input) return input.value;
  return '';
}

export class Uploader {
  /**
   * 构造函数
   * @param {Object} options
   * @param {string} options.uploadUrl 上传接口
   * @param {string} options.progressUrl 进度接口（可用 {taskId} 占位符）
   * @param {('silent'|'simple'|'full')} options.mode 进度显示模式
   * @param {function} options.onProgress 进度回调
   * @param {function} options.onSuccess 成功回调
   * @param {function} options.onError 失败回调
   */
  constructor({
    uploadUrl = '/api/ocr/upload/',
    progressUrl = '/api/ocr/progress/{taskId}/',
    mode = 'full',
    onProgress = null,
    onSuccess = null,
    onError = null,
  } = {}) {
    this.uploadUrl = uploadUrl;
    this.progressUrl = progressUrl;
    this.mode = mode;
    this.onProgress = onProgress;
    this.onSuccess = onSuccess;
    this.onError = onError;
    this.evtSource = null;
  }

  /**
   * 上传文件并自动监听进度
   * @param {File} file
   */
  async upload(file) {
    const formData = new FormData();
    formData.append('file', file);
    // 关键：加上 CSRF Token
    const csrfToken = getCsrfToken();
    const res = await fetch(this.uploadUrl, {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': csrfToken
      },
      credentials: 'include' // 确保 cookie 被带上
    });
    const data = await res.json();
    if (data.success && data.task_id) {
      this._listenProgress(data.task_id);
      return data;
    } else {
      if (this.onError) this.onError(data.message);
      throw new Error(data.message || '上传失败');
    }
  }

  /**
   * 监听后端图片处理进度
   * @param {string} taskId
   */
  _listenProgress(taskId) {
    if (this.evtSource) {
      this.evtSource.close();
    }
    const url = this.progressUrl.replace('{taskId}', taskId);
    this.evtSource = new EventSource(url);
    this.evtSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (this.onProgress) this.onProgress(data);

      if (this.mode === 'silent') {
        if (['SUCCESS', 'FAILED'].includes(data.status)) {
          if (this.onSuccess && data.status === 'SUCCESS') this.onSuccess(data);
          if (this.onError && data.status === 'FAILED') this.onError(data.message);
          this.evtSource.close();
        }
      } else if (this.mode === 'simple') {
        // 简单模式：只显示消息
        if (data.status === 'SUCCESS') {
          if (this.onSuccess) this.onSuccess(data);
          this.evtSource.close();
        } else if (data.status === 'FAILED') {
          if (this.onError) this.onError(data.message);
          this.evtSource.close();
        }
      } else {
        // 完整进度条
        if (data.status === 'SUCCESS') {
          if (this.onSuccess) this.onSuccess(data);
          this.evtSource.close();
        } else if (data.status === 'FAILED') {
          if (this.onError) this.onError(data.message);
          this.evtSource.close();
        }
      }
    };
    this.evtSource.onerror = (e) => {
      if (this.onError) this.onError('SSE连接异常');
      this.evtSource.close();
    };
  }

  /**
   * 主动关闭SSE连接
   */
  close() {
    if (this.evtSource) {
      this.evtSource.close();
      this.evtSource = null;
    }
  }
}

/*
<script type="module">
  import { Uploader } from '/static/js/uploader.js';

  const uploader = new Uploader({
    mode: 'full',
    onProgress: (data) => {
      document.getElementById('ocr-status').innerText = data.message;
      document.getElementById('ocr-progress').value = data.progress;
    },
    onSuccess: (data) => {
      alert('OCR完成: ' + (data.ocr_texts || ''));
    },
    onError: (msg) => {
      alert('出错: ' + msg);
    }
  });

  document.getElementById('upload-btn').onclick = function() {
    const file = document.getElementById('file-input').files[0];
    uploader.upload(file);
  };
</script>
*/