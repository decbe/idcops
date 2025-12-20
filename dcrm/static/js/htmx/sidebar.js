$(document).ready(function () {
    // 保存菜单状态到 localStorage
    $('.sidebar-menu').tree({
      saveState: true
    });
    
    // 添加滚动条
    $('.sidebar').slimScroll({
      height: '100%',
      railOpacity: 0.9
    });
    
    // 移动端自动收起菜单
    if ($(window).width() <= 767) {
      setTimeout(function() {
        if (!$('body').hasClass('sidebar-collapse')) {
          $('[data-toggle="push-menu"]').click();
        }
      }, 100);
    }
    
    // 记住展开的菜单
    $('.treeview').each(function() {
      if ($(this).hasClass('active')) {
        $(this).addClass('menu-open');
        $(this).find('> .treeview-menu').slideDown();
      }
    });
  });