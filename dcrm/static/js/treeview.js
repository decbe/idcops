document.addEventListener('DOMContentLoaded', function () {
    // 初始化树形结构
    function initializeTree() {
        // 初始状态：只隐藏非第一层级的子树
        document.querySelectorAll('.tree-children .tree-children tree-children').forEach(function (el) {
            el.style.display = 'none';
        });

        // 获取所有的树节点
        const treeNodes = document.querySelectorAll('.tree-node');

        // 为每个节点添加点击事件
        treeNodes.forEach(node => {
            node.addEventListener('click', function (e) {
                // 阻止事件冒泡
                e.stopPropagation();

                // 找到当前节点的li元素
                const parentLi = this.closest('li');

                // 找到图标元素
                const folderIcon = this.querySelector('.node-icon');

                // 找到下一个ul.tree-children元素（可能是兄弟元素或子元素）
                let childrenUl = parentLi.querySelector(':scope > ul.tree-children');
                if (!childrenUl) {
                    // 如果不是子元素，可能是下一个兄弟元素
                    let nextEl = parentLi.nextElementSibling;
                    if (nextEl && nextEl.classList.contains('tree-children')) {
                        childrenUl = nextEl;
                    }
                }

                // 切换展开/折叠状态
                if (childrenUl) {
                    const isExpanded = childrenUl.style.display !== 'none';
                    childrenUl.style.display = isExpanded ? 'none' : 'block';

                    // 切换图标
                    if (folderIcon) {
                        if (isExpanded) {
                            // folderIcon.closest('li').remove('active');
                            folderIcon.classList.remove('fa-folder-open');
                            folderIcon.classList.add('fa-folder');
                        } else {
                            folderIcon.closest('li').add('active');
                            folderIcon.classList.remove('fa-folder');
                            folderIcon.classList.add('fa-folder-open');
                        }
                    }
                }

                // 如果点击的是链接以外的区域，阻止默认行为
                if (!e.target.closest('a')) {
                    e.preventDefault();
                }
            });
        });
    }

    // 初始化所有树
    initializeTree();
});