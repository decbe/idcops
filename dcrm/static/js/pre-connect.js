// 获取所有预连接按钮
function initPreConnect() {
    document.querySelectorAll('a[data-handle-url]').forEach(button => {
        // 先移除已有的点击事件监听器
        button.removeEventListener('click', handlePreConnect);
        // 添加新的事件监听器
        button.addEventListener('click', handlePreConnect);
    });
}

// 将事件处理逻辑抽离出来
async function handlePreConnect(e) {
    // 阻止默认行为
    e.preventDefault();
    
    // 防止重复点击
    if (this.disabled) return;
    this.disabled = true;

    try {
        const csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]').value;
        const handleUrl = this.dataset.handleUrl;
        const portId = this.dataset.id;

        const response = await fetch(handleUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                port_id: portId
            })
        });

        const data = await response.json();

        if (response.ok) {
            if (data.reload) {
                window.location.reload();
            } else if (data.redirect_url) {
                window.location.href = data.redirect_url;
            } else {
                Toastify({
                    text: data.message || '操作成功',
                    duration: 3000,
                    gravity: "top",
                    position: "right",
                    style: {
                        background: "#28a745"
                    }
                }).showToast();
                // find the button and remove the disabled attribute
                const button = document.querySelector(`a[data-handle-url="${handleUrl}"]`);
                if (button) {
                    button.innerHTML = '已添加';
                    button.disabled = false;
                    button.classList.remove('label-info');
                    button.classList.add('label-success');
                }
            }
        } else {
            Toastify({
                text: data.error || '操作失败',
                duration: 5000,
                gravity: "top",
                position: "right",
                style: {
                    background: "#dc3545"
                }
            }).showToast();
        }
    } catch (error) {
        Toastify({
            text: error.message,
            duration: 5000,
        }).showToast();
    } finally {
        // 请求完成后重新启用按钮
        this.disabled = false;
    }
}

initPreConnect();