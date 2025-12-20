$(document).ready(function() {
    // 等待 AdminLTE 初始化完成
    setTimeout(function() {
        var pushMenu = $('[data-toggle="push-menu"]').data('lte.pushmenu');
        if (pushMenu) {
            var originalToggle = pushMenu.toggle;
            pushMenu.toggle = function() {
                var result = originalToggle.apply(this, arguments);
                
                if ($('body').hasClass('drawer-open')) {
                    const drawer = $('.table-drawer');
                    if ($('body').hasClass('sidebar-collapse')) {
                        drawer.css('width', 'calc(100% - 50px)');
                    } else {
                        if ($(window).width() <= 767) {
                            drawer.css('width', 'calc(100% - 50px)');
                        } else if ($(window).width() <= 1024) {
                            drawer.css('width', '60%');
                        } else {
                            drawer.css('width', '50%');
                        }
                    }
                }
                
                return result;
            };
        }
    }, 100);
    
    // 监听 body 类的变化
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.attributeName === 'class') {
                // 如果抽屉是打开状态，需要调整宽度
                if ($('body').hasClass('drawer-open')) {
                    const drawer = $('.table-drawer');
                    if ($('body').hasClass('sidebar-collapse')) {
                        drawer.css('width', 'calc(100% - 50px)');
                    } else {
                        // 恢复原始宽度
                        if ($(window).width() <= 767) {
                            drawer.css('width', 'calc(100% - 50px)');
                        } else if ($(window).width() <= 1024) {
                            drawer.css('width', '60%');
                        } else {
                            drawer.css('width', '50%');
                        }
                    }
                }
            }
        });
    });

    // 开始监听
    observer.observe(document.body, {
        attributes: true,
        attributeFilter: ['class']
    });
    
    // 打开抽屉
    function openDrawer(width, title) {
        const drawer = $('.table-drawer');
        
        // 计算宽度
        let finalWidth;
        if ($('body').hasClass('sidebar-collapse')) {
            // 菜单栏收缩时的宽度
            finalWidth = 'calc(100% - 50px)';  // 保持这个宽度
        } else {
            // 菜单栏展开时的宽度
            if ($(window).width() <= 767) {
                finalWidth = 'calc(100% - 50px)';
            } else if ($(window).width() <= 1024) {
                finalWidth = '60%';
            } else {
                finalWidth = '50%';
            }
        }
        
        // 设置宽度
        drawer.css('width', finalWidth);
        
        // 设置标题
        if (title) {
            $('#drawer-title').text(title);
        }
        
        // 添加打开状态
        $('body').addClass('drawer-open');
    }

    // 关闭抽屉
    function closeDrawer() {
        $('body').removeClass('drawer-open');
        
        // 清空内容
        $('.drawer-body').html(`
            <div class="text-center">
                <i class="fa fa-spinner fa-spin fa-2x"></i>
            </div>
        `);
    }

    // 修改选择器，只监听 data-toggle="drawer" 的元素
    $('body').on('click', '[data-toggle="drawer"]', function(e) {
        e.preventDefault();
        e.stopPropagation(); 
        const width = $(this).data('drawer-width');
        const title = $(this).data('drawer-title');
        openDrawer(width, title);
    });

    // 点击关闭按钮
    $('body').on('click', '.table-drawer .close', function(e) {
        e.preventDefault();
        e.stopPropagation(); // 阻止事件冒泡
        closeDrawer();
    });

    // ESC键关闭
    $(document).on('keydown', function(e) {
        if (e.keyCode === 27 && $('body').hasClass('drawer-open')) {
            closeDrawer();
        }
    });

    // 添加 HTMX 事件监听
    document.body.addEventListener('htmx:beforeRequest', function(evt) {
        if (evt.detail.elt.hasAttribute('data-toggle="drawer"')) {
            $('.drawer-body').html(`
                <div class="text-center">
                    <i class="fa fa-spinner fa-spin fa-2x"></i>
                </div>
            `);
        }
    });
});

(function($) {
    // 保存原始的 PushMenu
    var _PushMenu = $.fn.pushMenu.Constructor;
    
    // 创建新的构造函数
    var PushMenu = function(options) {
        _PushMenu.call(this, options);
    };
    
    // 继承原型
    PushMenu.prototype = Object.create(_PushMenu.prototype);
    
    // 重写 toggle 方法
    PushMenu.prototype.toggle = function() {
        // 调用原始的 toggle
        _PushMenu.prototype.toggle.call(this);
        
        // 处理抽屉
        if ($('body').hasClass('drawer-open')) {
            const drawer = $('.table-drawer');
            if ($('body').hasClass('sidebar-collapse')) {
                drawer.css('width', 'calc(100% - 50px)');
            } else {
                if ($(window).width() <= 767) {
                    drawer.css('width', 'calc(100% - 50px)');
                } else if ($(window).width() <= 1024) {
                    drawer.css('width', '60%');
                } else {
                    drawer.css('width', '50%');
                }
            }
        }
    };
    
    // 替换原始的构造函数
    $.fn.pushMenu.Constructor = PushMenu;
    
})(jQuery);