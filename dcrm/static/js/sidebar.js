// Drawer 控制器
const Drawer = {
    // 初始化
    init() {
        this.sidebar = $('.control-sidebar');
        this.bindEvents();
        this.setupHtmx();
    },

    // 绑定事件
    bindEvents() {
        // 监听抽屉打开事件
        $(document).on('click', '[data-toggle="control-sidebar"]', (e) => {
            const width = $(e.currentTarget).data('drawer-width') || 400;
            const title = $(e.currentTarget).data('drawer-title') || '';
            
            // 设置宽度和标题
            // this.sidebar.css('width', width + 'px');
            const finalWidth = /^[\d.]+(%|px)$/.test(width) ? width : `${width}px`;
            this.sidebar.css('width', finalWidth);
            $('.drawer-title').text(title);
        });
    },

    // 设置 HTMX 相关配置
    setupHtmx() {
        // HTMX 加载开始时显示加载状态
        htmx.on('htmx:beforeRequest', (evt) => {
            if (evt.detail.target.closest('.control-sidebar')) {
                this.showLoading();
            }
        });

        // HTMX 加载完成后隐藏加载状态
        htmx.on('htmx:afterRequest', (evt) => {
            if (evt.detail.target.closest('.control-sidebar')) {
                this.hideLoading();
            }
        });
    },

    // 显示加载状态
    showLoading() {
        this.sidebar.append('<div class="drawer-loading">加载中...</div>');
    },

    // 隐藏加载状态
    hideLoading() {
        this.sidebar.find('.drawer-loading').remove();
    }
};

// 页面加载完成后初始化
$(document).ready(() => {
    Drawer.init();
});